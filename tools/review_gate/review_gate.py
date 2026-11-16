"""Gate what Claude Code publishes on GitHub (ADR 0009).

Usage:
    review_gate.py pre-push              Git pre-push hook, declared for Claude's commands only by
                                         the `env` of .claude/settings.json: refuses to push a
                                         commit with no recorded review, or signed as Claude.
    review_gate.py hook                  PreToolUse hook of .claude/settings.json (git and gh
                                         commands, GitHub MCP tools): reads the hook JSON on stdin;
                                         exit code 2 refuses the tool call, with the reason on
                                         stderr.
    review_gate.py stamp --report FILE   Runs the checks of the CI on HEAD and records the review
                                         report as the stamp of HEAD.

The pre-push hook sees what git really pushes, whatever the command that runs git. The PreToolUse
hook refuses a text signed as Claude, a push with `--no-verify`, a push or a pull request while the
pre-push hook is not active, and the GitHub MCP tools that publish without git push.
Both guard against forgetting the review, not against a deliberate bypass (CLAUDE.md, section 6).
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every `uv run` step of .github/workflows/ci.yml, in the same order: a test keeps them in sync.
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

# Name of the pre-push hook in the `env` of .claude/settings.json (hook.<name>.command).
PRE_PUSH_HOOK = "dvb-review"

# The trailers and footers that Claude Code writes, not any person named Claude.
ATTRIBUTION = re.compile(
    r"(?:co-authored-by|signed-off-by):[^\n]*"
    r"(?:@anthropic\.com|\bclaude\s+(?:code|opus|sonnet|haiku|fable)\b)"
    r"|generated\s+with\s+\[?claude\s+code",
    re.IGNORECASE,
)

# A heredoc body is data, not words of the command (its text is still scanned for signatures).
HEREDOC = re.compile(
    r"(?P<head><<-?[ \t]*(?P<quote>['\"]?)(?P<tag>\w+)(?P=quote)[^\n]*\n)(?s:.*?)"
    r"^[ \t]*(?P=tag)[ \t]*$",
    re.MULTILINE,
)
# A command that looks like a push or a pull request: the pre-push hook must be active for it.
PUBLISH = re.compile(r"\bgit\b[^\n;&|]*\bpush\b|\bgh\b[^\n;&|]*\bpr\s+(?:create|new)\b")
TEXT_FILE_OPTIONS = ("-F", "--file", "--body-file")  # git commit, git tag, gh pr, gh issue

MCP_PUBLISH = re.compile(r"__(?:create_pr|create_pull_request|push_files|create_or_update_file)$")

REVIEW_MISSING = """Revue manquante : aucun tampon de revue pour {sha} ({ref}).
Avant de pousser, suivre la skill review-branch (.claude/skills/review-branch/SKILL.md) :
contrôles, relectures indépendantes par agents, corrections, rapport, puis
    uv run python tools/review_gate/review_gate.py stamp --report <rapport>
Ne pas contourner ce contrôle (CLAUDE.md, section 6). Une personne qui veut pousser sans revue
le fait elle-même, depuis son terminal."""

HOOK_INACTIVE = """Push ou PR refusé : le hook pre-push de revue n'est pas actif dans {cwd}.
Il demande git 2.54 ou plus récent et les variables GIT_CONFIG_* de .claude/settings.json
(session de Claude Code relancée après leur modification). Lancer la commande depuis le dossier
du dépôt ; si le hook reste inactif, le dire à la personne."""

NO_VERIFY_REFUSED = """Push refusé : `--no-verify` saute le hook pre-push de revue (ADR 0009).
Pousser sans cette option, après la skill review-branch."""

MCP_REFUSED = """Outil {tool} refusé : il publie sur GitHub sans passer par git push ni par la
revue (ADR 0009). Pousser avec `git push` et ouvrir la PR avec `gh pr create`, après la skill
review-branch."""

SIGNATURE_FOUND = """Signature de Claude refusée {where} : « {hit} ».
Claude ne se met jamais en co-auteur ni en signataire (CLAUDE.md, « Git et PR »).
Retirer cette ligne et recommencer."""

GATE_FAILED = """Le contrôle review_gate a échoué ({error}) : refus par prudence.
Relancer la commande depuis le dossier du dépôt ; si l'échec persiste, le dire à la personne.
Ne pas contourner ce contrôle."""


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


def stamp_path(repo: Path, sha: str) -> Path:
    return Path(repo, git(repo, "rev-parse", "--git-common-dir")) / STAMP_DIR / f"{sha}.md"


def push_refusal(repo: Path, updates: Sequence[str]) -> str | None:
    """Why the pre-push hook refuses the push, or None to let it go.

    Each update is `<local ref> <local sha> <remote ref> <remote sha>` (githooks, pre-push).
    """
    for update in updates:
        if not update.strip():
            continue
        local_ref, local_sha, *_ = update.split()
        if not local_sha.strip("0"):
            continue  # a deletion publishes nothing
        messages = git(repo, "log", "--format=%B", local_sha, "--not", "--remotes")
        if hit := find_attribution(messages):
            return SIGNATURE_FOUND.format(where="dans un commit à pousser", hit=hit)
        sha = git(repo, "rev-parse", f"{local_sha}^{{commit}}")
        if not stamp_path(repo, sha).is_file():
            return REVIEW_MISSING.format(sha=sha, ref=local_ref)
    return None


def shell_words(command: str) -> tuple[str, list[str]]:
    """The command without its heredoc bodies, and its words (split on blanks when an open quote
    defeats shlex)."""
    text = HEREDOC.sub(lambda match: match["head"], command)
    try:
        return text, shlex.split(text)
    except ValueError:
        return text, text.split()


def text_files(words: Sequence[str]) -> list[str]:
    """Files whose text the command publishes: -F, --file, --body-file."""
    files = [value for option, value in pairwise(words) if option in TEXT_FILE_OPTIONS]
    files += [
        value
        for option, _, value in (word.partition("=") for word in words)
        if value and option in TEXT_FILE_OPTIONS
    ]
    return [name for name in files if name != "-"]


def read_texts(cwd: Path, names: Sequence[str]) -> list[str]:
    """The text files that exist now. Git or gh reports the others; a file written by the same
    command is in the command text, which is scanned too."""
    texts: list[str] = []
    for name in names:
        try:
            texts.append((cwd / Path(name).expanduser()).read_text(encoding="utf-8"))
        except OSError, RuntimeError, UnicodeDecodeError:
            continue
    return texts


def pre_push_active(cwd: Path) -> bool:
    hooks = subprocess.run(
        ["git", "hook", "list", "pre-push"], cwd=cwd, capture_output=True, text=True, check=False
    )
    return PRE_PUSH_HOOK in hooks.stdout.split()


def bash_refusal(command: str, cwd: Path) -> str | None:
    """Why the hook refuses the Bash command, or None to let it run."""
    text, words = shell_words(command)
    for published in (command, *read_texts(cwd, text_files(words))):
        if hit := find_attribution(published):
            return SIGNATURE_FOUND.format(where="dans le texte", hit=hit)
    if {"push", "--no-verify"} <= set(words):
        return NO_VERIFY_REFUSED
    if PUBLISH.search(text) and not pre_push_active(cwd):
        return HOOK_INACTIVE.format(cwd=cwd)
    return None


def mcp_refusal(tool: str, tool_input: object) -> str | None:
    """Why the hook refuses the GitHub MCP tool call, or None to let it run."""
    if MCP_PUBLISH.search(tool):
        return MCP_REFUSED.format(tool=tool)
    text = json.dumps(tool_input, ensure_ascii=False).replace("\\n", "\n")
    if hit := find_attribution(text):
        return SIGNATURE_FOUND.format(where="dans le texte", hit=hit)
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
    sha = git(repo, "rev-parse", "HEAD")
    for check in checks:
        result = subprocess.run(check, cwd=repo, capture_output=True, text=True, check=False)
        if result.returncode:
            print(
                f"Échec de `{' '.join(check)}` :\n{result.stdout}{result.stderr}", file=sys.stderr
            )
            return 1
    if git(repo, "rev-parse", "HEAD") != sha or git(repo, "status", "--porcelain"):
        print("HEAD ou l'arbre a changé pendant les contrôles : relancer stamp.", file=sys.stderr)
        return 1
    path = stamp_path(repo, sha)
    path.parent.mkdir(exist_ok=True)
    header = (
        f"<!-- Revue de {sha} ({git(repo, 'branch', '--show-current')}), "
        f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC, {len(checks)} contrôles passés. -->\n\n"
    )
    path.write_text(header + text, encoding="utf-8")
    print(f"Revue enregistrée : {path}")
    return 0


def pre_push() -> int:
    try:  # git runs the hook at the root of the working tree
        reason = push_refusal(Path.cwd(), sys.stdin.read().splitlines())
    except Exception as error:  # a gate that crashes must not let a push through
        reason = GATE_FAILED.format(error=error)
    if reason:
        print(reason, file=sys.stderr)
        return 1
    return 0


def hook() -> int:
    try:
        payload = json.load(sys.stdin)
        tool, tool_input = payload["tool_name"], payload["tool_input"]
        if tool == "Bash":
            reason = bash_refusal(tool_input["command"], Path(payload.get("cwd") or Path.cwd()))
        else:
            reason = mcp_refusal(tool, tool_input)
    except Exception as error:  # a gate that crashes must not let a publication through
        reason = GATE_FAILED.format(error=error)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Gate what Claude Code publishes on GitHub.")
    commands = parser.add_subparsers(dest="command", required=True)
    pre_push_parser = commands.add_parser("pre-push", help="git pre-push hook: updates on stdin")
    pre_push_parser.add_argument("remote", nargs="*", help="remote name and URL, unused")
    commands.add_parser("hook", help="PreToolUse hook: hook JSON on stdin")
    stamp_parser = commands.add_parser("stamp", help="record the review of HEAD")
    stamp_parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "stamp":
        return stamp(REPO_ROOT, args.report, CHECKS)
    if args.command == "pre-push":
        return pre_push()
    return hook()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
