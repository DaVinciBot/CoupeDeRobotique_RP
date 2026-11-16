import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "review_gate.py"
CI_WORKFLOW = Path(__file__).parents[3] / ".github" / "workflows" / "ci.yml"

PASS = (sys.executable, "-c", "pass")
FAIL = (sys.executable, "-c", "raise SystemExit('check failed')")

REPORT = """# Revue

## Demande
Ajouter a.txt.

## Traçabilité
a.txt -> test_a.

## Contrôles
Tous passent.

## Relectures
dvb-request-reviewer : OK.

## Corrections
Aucune.

## Points ouverts
Aucun.
"""


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("review_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def commit(repo: Path, name: str, *messages: str) -> None:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", *[arg for message in messages for arg in ("-m", message)])


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "feat/x")
    git(path, "config", "user.email", "dev@example.com")
    git(path, "config", "user.name", "Dev")
    commit(path, "a.txt", "feat: add a")
    return path


@pytest.fixture
def report(tmp_path: Path) -> Path:
    path = tmp_path / "report.md"
    path.write_text(REPORT, encoding="utf-8")
    return path


def stamp_of_head(repo: Path) -> Path:
    common = Path(repo, git(repo, "rev-parse", "--git-common-dir"))
    return common / "dvb-review" / f"{git(repo, 'rev-parse', 'HEAD')}.md"


def record_review(repo: Path) -> None:
    path = stamp_of_head(repo)
    path.parent.mkdir(exist_ok=True)
    path.write_text(REPORT, encoding="utf-8")


def run_hook(repo: Path, command: str) -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "hook"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -u origin feat/x",
        "cd sub && git push",
        "FOO=1 git -C . push",
        "git add a.txt\ngit push",
        "env GIT_TRACE=1 git push",
        "bash -c 'git push --dry-run'",
        "git status; git push 2>&1 | tail -5",
        "gh pr create --fill",
    ],
)
def test_push_and_pull_request_need_a_review_of_head(repo: Path, command: str) -> None:
    result = run_hook(repo, command)

    assert result.returncode == 2
    assert "review-branch" in result.stderr
    assert git(repo, "rev-parse", "HEAD") in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "ls -la",
        'git commit -m "docs: explain git push"',
        "echo git push",
        "git log --oneline",
        "gh pr view 12",
    ],
)
def test_other_commands_pass(repo: Path, command: str) -> None:
    assert run_hook(repo, command).returncode == 0


def test_push_passes_once_head_is_reviewed(repo: Path) -> None:
    record_review(repo)

    assert run_hook(repo, "git push -u origin feat/x").returncode == 0
    assert run_hook(repo, "gh pr create --fill").returncode == 0


def test_review_of_an_older_commit_does_not_count(repo: Path) -> None:
    record_review(repo)
    commit(repo, "b.txt", "feat: add b")

    assert run_hook(repo, "git push").returncode == 2


@pytest.mark.parametrize(
    "text",
    [
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
        "co-authored-by: claude",
        "Signed-off-by: Claude <noreply@anthropic.com>",
        "Co-Authored-By: Someone <noreply@anthropic.com>",
        "Generated with Claude Code",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ],
)
def test_claude_signature_is_found(text: str) -> None:
    assert gate.find_attribution(f"feat: add a\n\n{text}\n") is not None


@pytest.mark.parametrize(
    "text",
    [
        "Co-Authored-By: Alice <alice@example.com>",
        "docs: run the review with Claude Code before each push",
        "refuse the co-authored-by lines that name the assistant",
    ],
)
def test_other_text_is_not_a_signature(text: str) -> None:
    assert gate.find_attribution(text) is None


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "feat: add b" -m "Co-Authored-By: Claude <noreply@anthropic.com>"',
        "git commit -m \"$(cat <<'EOF'\nfeat: add b\n\n"
        'Co-Authored-By: Claude <noreply@anthropic.com>\nEOF\n)"',
        'gh pr create --title "feat: b" --body "Done.\n\nGenerated with [Claude Code](https://claude.com)"',
    ],
)
def test_commit_and_pull_request_signed_by_claude_are_refused(repo: Path, command: str) -> None:
    record_review(repo)

    result = run_hook(repo, command)

    assert result.returncode == 2
    assert "co-auteur" in result.stderr


def test_body_file_signed_by_claude_is_refused(repo: Path, tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("## Description\n\nGenerated with Claude Code\n", encoding="utf-8")
    record_review(repo)

    result = run_hook(repo, f"gh pr create --title t --body-file {body}")

    assert result.returncode == 2
    assert "co-auteur" in result.stderr


def test_push_of_a_commit_signed_by_claude_is_refused(repo: Path) -> None:
    commit(repo, "b.txt", "feat: add b", "Co-Authored-By: Claude <noreply@anthropic.com>")
    record_review(repo)

    result = run_hook(repo, "git push")

    assert result.returncode == 2
    assert "co-auteur" in result.stderr


def test_stamp_records_the_report_for_head(repo: Path, report: Path) -> None:
    assert gate.stamp(repo, report, [PASS]) == 0

    recorded = stamp_of_head(repo).read_text(encoding="utf-8")
    assert git(repo, "rev-parse", "HEAD") in recorded
    assert REPORT in recorded
    assert run_hook(repo, "git push").returncode == 0


def test_stamp_refuses_a_dirty_tree(repo: Path, report: Path) -> None:
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")

    assert gate.stamp(repo, report, [PASS]) == 1
    assert not stamp_of_head(repo).exists()


def test_stamp_refuses_a_report_with_an_empty_section(repo: Path, report: Path) -> None:
    report.write_text(REPORT.replace("Aucune.\n", ""), encoding="utf-8")

    assert gate.stamp(repo, report, [PASS]) == 1
    assert not stamp_of_head(repo).exists()


def test_stamp_refuses_when_a_check_fails(repo: Path, report: Path) -> None:
    assert gate.stamp(repo, report, [PASS, FAIL]) == 1
    assert not stamp_of_head(repo).exists()


def test_checks_are_those_of_the_ci_python_job() -> None:
    ci_commands = re.findall(r"^\s*- run: (uv run .+)$", CI_WORKFLOW.read_text(), re.MULTILINE)

    assert [" ".join(check) for check in gate.CHECKS] == ci_commands
