"""Gate the git and gh commands that Claude Code runs (ADR 0009).

Usage:
    review_gate.py hook                  PreToolUse hook of .claude/settings.json: reads the hook
                                         JSON on stdin; exit code 2 refuses the command, with the
                                         reason on stderr.
    review_gate.py stamp --report FILE   Runs the checks of the CI on HEAD and records the review
                                         report as the stamp of HEAD.

The hook refuses:
- `git push` and `gh pr create` while no review is recorded for HEAD;
- a commit, a push, a pull request or an issue whose text names Claude as co-author or signer.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The python job of .github/workflows/ci.yml, in the same order: a test keeps them in sync.
CHECKS: tuple[tuple[str, ...], ...] = (
    ("uv", "run", "--frozen", "ruff", "format", "--check"),
    ("uv", "run", "--frozen", "ruff", "check"),
    ("uv", "run", "--frozen", "pyright"),
    ("uv", "run", "--frozen", "lint-imports"),
    ("uv", "run", "--frozen", "python", "tools/core_check/theme_words.py"),
    ("uv", "run", "--frozen", "python", "tools/core_check/theme_coordinates.py"),
    ("uv", "run", "--frozen", "pytest"),
)

# Sections of the review report, each with some text (skill review-branch).
REPORT_SECTIONS = (
    "Demande",
    "Traçabilité",
    "Contrôles",
    "Relectures",
    "Corrections",
    "Points ouverts",
)

# Stamps live in the git directory: never tracked, shared by the worktrees of the clone.
STAMP_DIR = "dvb-review"

# Claude never signs a commit, a pull request or an issue (CLAUDE.md, "Git et PR").
ATTRIBUTION = re.compile(
    r"(?:co-authored-by|signed-off-by):[^\n]*(?:claude|anthropic)|generated with \[?claude code",
    re.IGNORECASE,
)

PUNCTUATION = ";&|()<>\n"
SEPARATORS = frozenset(";&|()\n")  # a token made of these chars ends a simple command
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = frozenset({"builtin", "command", "env", "exec", "nohup", "time"})
SHELLS = frozenset({"bash", "sh", "zsh"})
GIT_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
GIT_TEXT_COMMANDS = frozenset({"commit", "merge", "notes", "tag"})
GH_TEXT_COMMANDS = frozenset(
    {
        ("issue", "comment"),
        ("issue", "create"),
        ("issue", "edit"),
        ("pr", "comment"),
        ("pr", "create"),
        ("pr", "edit"),
        ("pr", "review"),
    }
)
TEXT_FILE_OPTIONS = ("-F", "--file", "--body-file")

REVIEW_MISSING = """Revue manquante : aucun tampon de revue pour HEAD {sha}.
Avant `git push` ou `gh pr create`, suivre la skill review-branch
(.claude/skills/review-branch/SKILL.md) : contrôles, relectures indépendantes par agents,
corrections, rapport, puis
    uv run python tools/review_gate/review_gate.py stamp --report <rapport>
Ne pas contourner ce contrôle (CLAUDE.md, section 6). Une personne qui veut pousser sans revue
le fait elle-même, depuis son terminal."""

SIGNATURE_FOUND = """Signature de Claude refusée {where} : « {hit} ».
Claude ne se met jamais en co-auteur ni en signataire (CLAUDE.md, « Git et PR »).
Retirer cette ligne et recommencer."""


@dataclass(frozen=True, slots=True)
class Analysis:
    """What a shell command does that the gate cares about."""

    pushes: bool
    opens_pull_request: bool
    writes_text: bool
    text_files: tuple[str, ...]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def find_attribution(text: str) -> str | None:
    """The line of the text that signs it as Claude, if any."""
    match = ATTRIBUTION.search(text)
    if not match:
        return None
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    return text[start : len(text) if end == -1 else end].strip()


def strip_prefix(words: list[str]) -> list[str]:
    """Drop the variable assignments and wrappers (env, command...) before the program name."""
    i = 0
    while i < len(words) and (
        ASSIGNMENT.match(words[i]) or words[i] in WRAPPERS or (i and words[i].startswith("-"))
    ):
        i += 1
    return words[i:]


def simple_commands(command: str) -> list[list[str]]:
    """Split a shell command line into its simple commands, including those of `bash -c`."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:  # unbalanced quotes: the shell refuses the line too
        return []
    groups: list[list[str]] = [[]]
    for token in tokens:
        if set(token) <= SEPARATORS:
            groups.append([])
        else:
            groups[-1].append(token)
    commands: list[list[str]] = []
    for group in groups:
        words = strip_prefix(group)
        if not words:
            continue
        commands.append(words)
        if Path(words[0]).name in SHELLS:
            for i, word in enumerate(words[1:-1], start=1):
                if word.startswith("-") and not word.startswith("--") and "c" in word:
                    commands += simple_commands(words[i + 1])
                    break
    return commands


def git_arguments(words: list[str]) -> list[str]:
    """Arguments after `git` and its global options, or [] when the program is not git."""
    if Path(words[0]).name != "git":
        return []
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in GIT_OPTIONS_WITH_VALUE else 1
    return words[i:]


def option_values(words: list[str], options: Sequence[str]) -> list[str]:
    values: list[str] = []
    for i, word in enumerate(words):
        if word in options and i + 1 < len(words):
            values.append(words[i + 1])
        values += [word.split("=", 1)[1] for option in options if word.startswith(f"{option}=")]
    return [value for value in values if value != "-"]


def analyze(command: str) -> Analysis:
    pushes = opens_pull_request = writes_text = False
    text_files: list[str] = []
    for words in simple_commands(command):
        arguments = git_arguments(words)
        gh_command = tuple(words[1:3]) if Path(words[0]).name == "gh" else ()
        if arguments[:1] == ["push"]:
            pushes = True
        elif arguments and arguments[0] in GIT_TEXT_COMMANDS:
            writes_text = True
            text_files += option_values(arguments, TEXT_FILE_OPTIONS)
        elif gh_command in GH_TEXT_COMMANDS:
            opens_pull_request |= gh_command == ("pr", "create")
            writes_text = True
            text_files += option_values(words, TEXT_FILE_OPTIONS)
    return Analysis(pushes, opens_pull_request, writes_text, tuple(text_files))


def stamp_path(repo: Path, sha: str) -> Path:
    return Path(repo, git(repo, "rev-parse", "--git-common-dir")) / STAMP_DIR / f"{sha}.md"


def refusal(command: str, cwd: Path) -> str | None:
    """Why the hook refuses the command, or None to let it run."""
    analysis = analyze(command)
    if analysis.writes_text:
        texts = [
            command,
            *(Path(cwd, name).read_text(encoding="utf-8") for name in analysis.text_files),
        ]
        for text in texts:
            if hit := find_attribution(text):
                return SIGNATURE_FOUND.format(where="dans le texte", hit=hit)
    if analysis.pushes:
        unpushed = git(cwd, "log", "HEAD", "--not", "--remotes", "--format=%B")
        if hit := find_attribution(unpushed):
            return SIGNATURE_FOUND.format(where="dans un commit à pousser", hit=hit)
    if analysis.pushes or analysis.opens_pull_request:
        sha = git(cwd, "rev-parse", "HEAD")
        if not stamp_path(cwd, sha).exists():
            return REVIEW_MISSING.format(sha=sha)
    return None


def missing_sections(report: str) -> list[str]:
    """Required sections of the report that are absent or empty."""
    bodies: dict[str, int] = {}
    current = ""
    for line in report.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            bodies.setdefault(current, 0)
        elif current and line.strip():
            bodies[current] += 1
    return [section for section in REPORT_SECTIONS if not bodies.get(section)]


def stamp(repo: Path, report: Path, checks: Sequence[Sequence[str]]) -> int:
    """Record the review of HEAD: clean tree, complete report, green checks."""
    if git(repo, "status", "--porcelain"):
        print(
            "Arbre de travail modifié : commiter d'abord, la revue porte sur HEAD.", file=sys.stderr
        )
        return 1
    text = report.read_text(encoding="utf-8")
    if missing := missing_sections(text):
        print(f"Sections absentes ou vides du rapport : {', '.join(missing)}.", file=sys.stderr)
        return 1
    for check in checks:
        result = subprocess.run(check, cwd=repo, capture_output=True, text=True, check=False)
        if result.returncode:
            print(
                f"Échec de `{' '.join(check)}` :\n{result.stdout}{result.stderr}", file=sys.stderr
            )
            return 1
    sha = git(repo, "rev-parse", "HEAD")
    path = stamp_path(repo, sha)
    path.parent.mkdir(exist_ok=True)
    header = (
        f"<!-- Revue de {sha} ({git(repo, 'branch', '--show-current')}), "
        f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC, {len(checks)} contrôles passés. -->\n\n"
    )
    path.write_text(header + text, encoding="utf-8")
    print(f"Revue enregistrée : {path}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Gate the git and gh commands of Claude Code.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hook", help="PreToolUse hook: hook JSON on stdin")
    stamp_parser = commands.add_parser("stamp", help="record the review of HEAD")
    stamp_parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "stamp":
        return stamp(REPO_ROOT, args.report, CHECKS)
    payload = json.load(sys.stdin)
    reason = refusal(payload["tool_input"]["command"], Path(payload.get("cwd") or Path.cwd()))
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
