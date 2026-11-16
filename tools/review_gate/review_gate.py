"""Gate what Claude Code publishes on GitHub (ADR 0009).

Usage:
    review_gate.py hook                  PreToolUse hook of .claude/settings.json: reads the hook
                                         JSON on stdin; exit code 2 refuses the tool call, with the
                                         reason on stderr.
    review_gate.py stamp --report FILE   Runs the checks of the CI on HEAD and records the review
                                         report as the stamp of HEAD.

The hook sees every Bash command and the GitHub tools of the MCP servers. It refuses:
- `git push` and `gh pr create` while no review is recorded for HEAD, or in a form it cannot
  follow: another directory, another branch, HEAD moved by the same command, unreadable syntax;
- a push or a pull request made with a GitHub MCP tool, which no review covers;
- a commit, a push, a pull request, an issue or a comment whose text signs it as Claude.
It guards against forgetting the review, not against a deliberate bypass (CLAUDE.md, section 6).
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

# The trailers and footers that Claude Code writes, not any person named Claude.
ATTRIBUTION = re.compile(
    r"(?:co-authored-by|signed-off-by):[^\n]*"
    r"(?:@anthropic\.com|\bclaude\s+(?:code|opus|sonnet|haiku|fable)\b)"
    r"|generated\s+with\s+\[?claude\s+code",
    re.IGNORECASE,
)

# A heredoc body is data, not shell: it is dropped before parsing (its text is still scanned).
HEREDOC = re.compile(
    r"(?P<head><<-?[ \t]*(?P<quote>['\"]?)(?P<tag>\w+)(?P=quote)[^\n]*\n)(?s:.*?)"
    r"^[ \t]*(?P=tag)[ \t]*$",
    re.MULTILINE,
)
# Used only when the parser fails, to know whether the command publishes.
PUBLISH = re.compile(r"\bgit\b[^\n;&|]*\bpush\b|\bgh\b[^\n;&|]*\bpr\s+(?:create|new)\b")

PUNCTUATION = ";&|()<>\n"
SEPARATORS = frozenset(";&|()\n")  # a token made of these chars ends a simple command
REDIRECTIONS = frozenset("<>&")  # a token made of these chars redirects: it and its target go
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = frozenset(
    {"builtin", "command", "env", "exec", "nice", "nohup", "noglob", "stdbuf", "sudo", "time"}
    | {"timeout", "xargs"}
)
SHELLS = frozenset({"bash", "sh", "zsh"})
SHELL_COMMAND_FLAG = re.compile(r"-[a-z]*c[a-z]*")  # bash -c, bash -lc...
PROGRAMS = SHELLS | {"eval", "gh", "git"}  # what a wrapper may run that the gate looks into
DIRECTORY_COMMANDS = frozenset({"cd", "popd", "pushd"})

GIT_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
GIT_UNFOLLOWED = ("--git-dir", "--work-tree")
GIT_HEAD_MOVERS = frozenset(
    {"am", "checkout", "cherry-pick", "commit", "merge", "pull", "rebase", "reset", "revert"}
    | {"switch"}
)
GIT_TEXT_COMMANDS = frozenset({"commit", "merge", "notes", "tag"})
PUSH_OPTIONS_WITH_VALUE = frozenset({"-o", "--push-option", "--receive-pack", "--exec", "--repo"})
PUSH_UNFOLLOWED = frozenset({"--all", "--branches", "--mirror", "--tags", "--delete", "-d"})

GH_OPTIONS_WITH_VALUE = frozenset({"-R", "--repo"})
GH_PULL_REQUEST = frozenset({("pr", "create"), ("pr", "new")})
GH_TEXT_COMMANDS = GH_PULL_REQUEST | {
    ("issue", "comment"),
    ("issue", "create"),
    ("issue", "edit"),
    ("pr", "comment"),
    ("pr", "edit"),
    ("pr", "review"),
}
TEXT_FILE_OPTIONS = ("-F", "--file", "--body-file")

MCP_PUBLISH = re.compile(
    r"__(?:create_pr|create_pull_request|merge_pr|merge_pull_request|push_files"
    r"|create_or_update_file|delete_file)$"
)

REVIEW_MISSING = """Revue manquante : aucun tampon de revue pour HEAD {sha}.
Avant `git push` ou `gh pr create`, suivre la skill review-branch
(.claude/skills/review-branch/SKILL.md) : contrôles, relectures indépendantes par agents,
corrections, rapport, puis
    uv run python tools/review_gate/review_gate.py stamp --report <rapport>
Ne pas contourner ce contrôle (CLAUDE.md, section 6). Une personne qui veut pousser sans revue
le fait elle-même, depuis son terminal."""

FORM_REFUSED = """Push ou PR refusé : {problem}.
Le contrôle de revue ne suit que `git push` et `gh pr create` lancés pour la branche courante,
depuis le dossier de la session, dans une commande qui ne déplace pas HEAD. Les lancer seuls,
après la revue du HEAD à publier (skill review-branch). Ne pas contourner ce contrôle."""

MCP_REFUSED = """Outil {tool} refusé : il publie sur GitHub sans passer par la revue (ADR 0009).
Pousser avec `git push` et ouvrir la PR avec `gh pr create`, après la skill review-branch."""

SIGNATURE_FOUND = """Signature de Claude refusée {where} : « {hit} ».
Claude ne se met jamais en co-auteur ni en signataire (CLAUDE.md, « Git et PR »).
Retirer cette ligne et recommencer."""

GATE_FAILED = """Le contrôle review_gate a échoué ({error}) : commande refusée par prudence.
La lancer plus simplement (seule, depuis le dossier du dépôt) ; si l'échec persiste, le dire à la
personne. Ne pas contourner ce contrôle."""


@dataclass(frozen=True, slots=True)
class Analysis:
    """What a shell command does that the gate cares about."""

    publishes: bool  # git push or gh pr create
    pushes: bool  # git push: its commits are scanned for signatures
    readable: bool  # False when the syntax defeats the parser: publishes then comes from PUBLISH
    moves_head: bool  # git commit, rebase...: HEAD would change before the publication
    directories: tuple[str, ...]  # targets of cd, pushd, popd and git -C
    unfollowed: tuple[str, ...]  # options the gate cannot follow: --all, --git-dir...
    revisions: tuple[str, ...]  # what is published: sources of the refspecs, gh --head
    writes_text: bool  # commit, tag, pull request, issue or comment
    text_files: tuple[str, ...]  # files read by -F, --file, --body-file


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
    """The words from the program on: variable assignments and wrappers (env, timeout...) go."""
    i = 0
    while i < len(words) and ASSIGNMENT.match(words[i]):
        i += 1
    if i < len(words) and Path(words[i]).name in WRAPPERS:
        # A wrapper has options of its own: what it runs is the next git, gh or shell.
        programs = (j for j in range(i + 1, len(words)) if Path(words[j]).name in PROGRAMS)
        return words[next(programs, len(words)) :]
    return words[i:]


def simple_commands(command: str) -> list[list[str]] | None:
    """The simple commands of a shell line, with those run by `bash -c` and `eval`.

    None when the line defeats the parser (a quote left open outside a heredoc, for example).
    """
    text = drop_heredoc_bodies(command).replace("`", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""  # shlex comments differ from the shell's: handled below
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    groups: list[list[str]] = [[]]
    comment = redirected = False
    for token in tokens:
        if set(token) <= SEPARATORS:
            comment = comment and "\n" not in token
            redirected = False
            groups.append([])
        elif comment or token.startswith("#"):
            comment = True
        elif set(token) <= REDIRECTIONS:
            if groups[-1] and groups[-1][-1].isdigit():
                groups[-1].pop()  # the file descriptor of 2>&1
            redirected = True
        elif redirected:
            redirected = False  # the target of the redirection
        else:
            groups[-1].append(token)
    commands: list[list[str]] = []
    for group in groups:
        words = strip_prefix(group)
        if not words:
            continue
        commands.append(words)
        program = Path(words[0]).name
        if program == "eval":
            inner = simple_commands(" ".join(words[1:]))
        elif program in SHELLS:
            flags = [i for i, word in enumerate(words[:-1]) if SHELL_COMMAND_FLAG.fullmatch(word)]
            inner = simple_commands(words[flags[0] + 1]) if flags else []
        else:
            inner = []
        if inner is None:
            return None
        commands += inner
    return commands


def split_program(
    words: list[str], program: str, options: frozenset[str]
) -> tuple[list[str], list[str]]:
    """Global options and arguments of `program`, or two empty lists for another program."""
    if Path(words[0]).name != program:
        return [], []
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in options else 1
    return words[1:i], words[i:]


def option_values(words: list[str], options: Sequence[str]) -> list[str]:
    values: list[str] = []
    for i, word in enumerate(words):
        if word in options and i + 1 < len(words):
            values.append(words[i + 1])
        values += [word.split("=", 1)[1] for option in options if word.startswith(f"{option}=")]
    return [value for value in values if value != "-"]


def positionals(words: list[str], options: frozenset[str]) -> list[str]:
    """The words that are neither options nor values of options."""
    found: list[str] = []
    i = 0
    while i < len(words):
        if not words[i].startswith("-"):
            found.append(words[i])
        i += 2 if words[i] in options else 1
    return found


def drop_heredoc_bodies(command: str) -> str:
    return HEREDOC.sub(lambda match: match["head"], command)


def analyze(command: str) -> Analysis:
    commands = simple_commands(command)
    if commands is None:
        publishes = bool(PUBLISH.search(drop_heredoc_bodies(command)))
        return Analysis(publishes, publishes, False, False, (), (), (), True, ())
    publishes = pushes = moves_head = writes_text = False
    directories: list[str] = []
    unfollowed: list[str] = []
    revisions: list[str] = []
    text_files: list[str] = []
    for words in commands:
        program = Path(words[0]).name
        if program in DIRECTORY_COMMANDS:
            moves_back = program == "popd" or (program == "pushd" and len(words) == 1)
            directories.append("-" if moves_back else words[1] if len(words) > 1 else "~")
        options, arguments = split_program(words, "git", GIT_OPTIONS_WITH_VALUE)
        directories += option_values(options, ("-C",))
        unfollowed += [word for word in options if word.split("=", 1)[0] in GIT_UNFOLLOWED]
        if arguments[:1] == ["push"]:
            publishes = pushes = True
            unfollowed += [word for word in arguments if word in PUSH_UNFOLLOWED]
            specs = positionals(arguments[1:], PUSH_OPTIONS_WITH_VALUE)[1:]
            revisions += [spec.lstrip("+").split(":", 1)[0] for spec in specs] or ["HEAD"]
        moves_head |= bool(arguments) and arguments[0] in GIT_HEAD_MOVERS
        if arguments and arguments[0] in GIT_TEXT_COMMANDS:
            writes_text = True
            text_files += option_values(arguments, TEXT_FILE_OPTIONS)
        _, gh_arguments = split_program(words, "gh", GH_OPTIONS_WITH_VALUE)
        if tuple(gh_arguments[:2]) in GH_PULL_REQUEST:
            publishes = True
            heads = option_values(gh_arguments, ("-H", "--head"))
            revisions += [head.rsplit(":", 1)[-1] for head in heads] or ["HEAD"]
        if tuple(gh_arguments[:2]) in GH_TEXT_COMMANDS:
            writes_text = True
            text_files += option_values(gh_arguments, TEXT_FILE_OPTIONS)
    return Analysis(
        publishes,
        pushes,
        True,
        moves_head,
        tuple(directories),
        tuple(unfollowed),
        tuple(revisions),
        writes_text,
        tuple(text_files),
    )


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


def is_directory(cwd: Path, directory: str) -> bool:
    """Whether `cd directory` from cwd stays in cwd."""
    if directory == "-" or "$" in directory:
        return False
    try:
        return (cwd / Path(directory).expanduser()).resolve() == cwd.resolve()
    except RuntimeError:  # unknown user in ~user
        return False


def form_problem(analysis: Analysis, cwd: Path) -> str | None:
    """Why the gate cannot tell what a publication publishes, if it cannot."""
    if not analysis.readable:
        return "le contrôle ne sait pas lire cette commande (guillemet ouvert hors d'un heredoc ?)"
    if analysis.moves_head:
        return "la même commande déplace HEAD (commit, rebase, pull...)"
    if analysis.unfollowed:
        return f"options que le contrôle ne suit pas : {' '.join(analysis.unfollowed)}"
    for directory in analysis.directories:
        if not is_directory(cwd, directory):
            return f"elle change de dossier ({directory})"
    current = {"HEAD", "@", git(cwd, "branch", "--show-current")} - {""}
    for revision in analysis.revisions:
        if revision.removeprefix("refs/heads/") not in current:
            return f"elle publie autre chose que la branche courante ({revision or 'suppression'})"
    return None


def stamp_path(repo: Path, sha: str) -> Path:
    return Path(repo, git(repo, "rev-parse", "--git-common-dir")) / STAMP_DIR / f"{sha}.md"


def refusal(command: str, cwd: Path) -> str | None:
    """Why the hook refuses the Bash command, or None to let it run."""
    analysis = analyze(command)
    if analysis.writes_text:
        for text in (command, *read_texts(cwd, analysis.text_files)):
            if hit := find_attribution(text):
                return SIGNATURE_FOUND.format(where="dans le texte", hit=hit)
    if not analysis.publishes:
        return None
    if problem := form_problem(analysis, cwd):
        return FORM_REFUSED.format(problem=problem)
    if analysis.pushes:
        unpushed = git(cwd, "log", "HEAD", "--not", "--remotes", "--format=%B")
        if hit := find_attribution(unpushed):
            return SIGNATURE_FOUND.format(where="dans un commit à pousser", hit=hit)
    sha = git(cwd, "rev-parse", "HEAD")
    if not stamp_path(cwd, sha).exists():
        return REVIEW_MISSING.format(sha=sha)
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


def hook() -> int:
    try:
        payload = json.load(sys.stdin)
        tool, tool_input = payload["tool_name"], payload["tool_input"]
        if tool == "Bash":
            cwd = Path(payload.get("cwd") or Path.cwd())
            reason = refusal(tool_input["command"], cwd)
        else:
            reason = mcp_refusal(tool, tool_input)
    except Exception as error:  # a gate that crashes must not let a push through
        reason = GATE_FAILED.format(error=error)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Gate what Claude Code publishes on GitHub.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hook", help="PreToolUse hook: hook JSON on stdin")
    stamp_parser = commands.add_parser("stamp", help="record the review of HEAD")
    stamp_parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "stamp":
        return stamp(REPO_ROOT, args.report, CHECKS)
    return hook()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
