import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "review_gate.py"
CI_WORKFLOW = Path(__file__).parents[3] / ".github" / "workflows" / "ci.yml"

PASS = (sys.executable, "-c", "pass")
FAIL = (sys.executable, "-c", "raise SystemExit('check failed')")
COMMITS = (
    sys.executable,
    "-c",
    "import subprocess; subprocess.run(['git', 'commit', '-q', '--allow-empty', '-m', 'x'])",
)

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

SIGNED = "Co-Authored-By: Claude <noreply@anthropic.com>"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("review_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load()


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """No user or system git config, no GIT_* variable left by a calling git hook."""
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
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


def run_tool(payload: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "hook"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def run_hook(cwd: Path, command: str) -> subprocess.CompletedProcess[str]:
    return run_tool({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -u origin feat/x",
        "git push origin HEAD",
        "FOO=1 git -C . push",
        "git add a.txt\ngit push",
        "git status; git push 2>&1 | tail -5",
        "git add -A  # stage everything\ngit push",
        "git add . # don't forget\ngit push",
        'echo "#x"; git push',
        "bash <<'EOF'\ngit push\nEOF",
        "cat <<'EOF' | sh\ngit push\nEOF",
        "env GIT_TRACE=1 git push",
        "env -u FOO git push",
        "timeout 60 git push",
        "nice -n 5 git push",
        "bash -c 'git push --dry-run'",
        "eval 'git push'",
        "echo `git push`",
        "gh pr create --fill",
        "gh pr new --fill",
        "gh -R owner/repo pr create --fill",
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
        "git push",
        "git push -u origin feat/x",
        "git push --force-with-lease origin HEAD:refs/heads/feat/x",
        "git -C . push",
        "git status && git push 2>&1 | tail -5",
        "gh pr create --fill",
        "gh -R owner/repo pr create --head feat/x --fill",
    ],
)
def test_push_and_pull_request_pass_once_head_is_reviewed(repo: Path, command: str) -> None:
    record_review(repo)

    assert run_hook(repo, command).returncode == 0


def test_cd_to_the_same_directory_is_followed(repo: Path) -> None:
    record_review(repo)

    assert run_hook(repo, f"cd {shlex.quote(str(repo))} && git push").returncode == 0


@pytest.mark.parametrize(
    "command",
    [
        "git commit -am 'fix: after review' && git push",
        "git commit -m wip#1; git push",
        "git commit -F - <<'EOF'\nfix: don't break\nEOF\ngit push",
        "git commit --amend --no-edit && git push --force-with-lease",
        "git pull --rebase origin dev && git push",
        "cd .. && git push",
        "git -C ../other push",
        "git --git-dir=../other/.git push",
        "git push origin other",
        "git push origin :old",
        "git push --all",
        "git push --tags",
        "gh pr create --head other --fill",
        "printf other | xargs git push origin",
    ],
)
def test_publication_in_a_form_the_gate_cannot_follow_is_refused(repo: Path, command: str) -> None:
    record_review(repo)

    result = run_hook(repo, command)

    assert result.returncode == 2
    assert "Push ou PR refusé" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "ls -la",
        "cd .. && ls",
        'git commit -m "docs: explain git push"',
        'git commit -m "fix: push handler"',
        "git commit -m wip#1",
        "git commit -m '#12 fix'",
        "echo $# arguments",
        "cat > deploy.sh <<'EOF'\n#!/bin/sh\necho it's\ngit push origin x\nEOF",
        "git commit -F missing.txt",
        "echo git push",
        "git log --oneline",
        'git log --grep "git push"',
        "git stash push",
        "git pull --rebase",
        "gh pr view 12",
        "gh pr list",
        "cat > notes.md <<'EOF'\nl'évitement\n    git push origin x\nEOF\ngit add notes.md",
    ],
)
def test_other_commands_pass(repo: Path, command: str) -> None:
    assert run_hook(repo, command).returncode == 0


def test_merge_is_left_to_a_person(repo: Path) -> None:
    record_review(repo)

    result = run_hook(repo, "gh pr merge 12 --squash")

    assert result.returncode == 2
    assert "Merge refusé" in result.stderr


def test_review_of_an_older_commit_does_not_count(repo: Path) -> None:
    record_review(repo)
    commit(repo, "b.txt", "feat: add b")

    assert run_hook(repo, "git push").returncode == 2


def test_review_is_shared_by_the_worktrees(repo: Path, tmp_path: Path) -> None:
    git(repo, "worktree", "add", "-q", "-b", "feat/y", str(tmp_path / "wt"))
    record_review(repo)

    assert run_hook(tmp_path / "wt", "git push").returncode == 0


def test_gate_refuses_a_push_it_cannot_check(tmp_path: Path) -> None:
    result = run_hook(tmp_path, "git push")

    assert result.returncode == 2
    assert "review_gate a échoué" in result.stderr


@pytest.mark.parametrize(
    "text",
    [
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
        SIGNED,
        "Signed-off-by: Claude Code",
        "Co-Authored-By: Someone <noreply@anthropic.com>",
        "Generated with Claude Code",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ],
)
def test_claude_signature_is_found(text: str) -> None:
    assert gate.find_attribution(f"feat: add a\n\n{text}\n") == text


@pytest.mark.parametrize(
    "text",
    [
        "Co-Authored-By: Alice <alice@example.com>",
        "Co-Authored-By: Claude Dupont <claude.dupont@example.com>",
        "docs: refuse lines like Co-Authored-By: Claude",
        "docs: run the review with Claude Code before each push",
        "refuse the co-authored-by lines that name the assistant",
    ],
)
def test_other_text_is_not_a_signature(text: str) -> None:
    assert gate.find_attribution(text) is None


@pytest.mark.parametrize(
    "command",
    [
        f'git commit -m "feat: add b" -m "{SIGNED}"',
        f"git commit -m \"$(cat <<'EOF'\nfeat: add b\n\n{SIGNED}\nEOF\n)\"",
        f"git commit -F - <<'EOF'\nfeat: don't break\n\n{SIGNED}\nEOF",
        'gh pr create --title "feat: b" --body "Done.\n\nGenerated with [Claude Code](https://x)"',
        f"gh issue comment 3 --body '{SIGNED}'",
    ],
)
def test_text_signed_by_claude_is_refused(repo: Path, command: str) -> None:
    result = run_hook(repo, command)

    assert result.returncode == 2
    assert "Signature de Claude" in result.stderr


@pytest.mark.parametrize("name", ["body.md", "{tmp}/body.md"])
def test_body_file_signed_by_claude_is_refused(repo: Path, tmp_path: Path, name: str) -> None:
    path = name.format(tmp=tmp_path)
    (repo / path).write_text(f"## Description\n\n{SIGNED}\n", encoding="utf-8")

    result = run_hook(repo, f"gh pr create --title t --body-file {path}")

    assert result.returncode == 2
    assert "Signature de Claude" in result.stderr


def test_missing_body_file_is_left_to_gh(repo: Path) -> None:
    record_review(repo)

    assert run_hook(repo, "gh pr create --title t --body-file missing.md").returncode == 0


def test_push_of_a_commit_signed_by_claude_is_refused(repo: Path) -> None:
    commit(repo, "b.txt", "feat: add b", SIGNED)
    record_review(repo)

    result = run_hook(repo, "git push")

    assert result.returncode == 2
    assert "Signature de Claude" in result.stderr


@pytest.mark.parametrize(
    "tool",
    [
        "mcp__plugin_github_github__create_pull_request",
        "mcp__plugin_github_github__push_files",
        "mcp__claude_ai_GitHub__create_pr",
        "mcp__claude_ai_GitHub__create_or_update_file",
    ],
)
def test_github_tools_that_publish_are_refused(tool: str) -> None:
    result = run_tool({"tool_name": tool, "tool_input": {"title": "feat: x"}})

    assert result.returncode == 2
    assert "sans passer par la revue" in result.stderr


def test_github_tool_text_signed_by_claude_is_refused() -> None:
    body = {"title": "Bug", "body": f"Steps.\n\n{SIGNED}"}

    result = run_tool({"tool_name": "mcp__plugin_github_github__create_issue", "tool_input": body})

    assert result.returncode == 2
    assert "Signature de Claude" in result.stderr


def test_other_github_tools_pass() -> None:
    body = {"title": "Bug", "body": "Steps.\n\nCo-Authored-By: Claude Dupont <c@example.com>"}

    result = run_tool({"tool_name": "mcp__plugin_github_github__create_issue", "tool_input": body})

    assert result.returncode == 0


def test_stamp_records_the_report_for_head(repo: Path, report: Path) -> None:
    assert gate.stamp(repo, report, [PASS]) == 0

    recorded = stamp_of_head(repo).read_text(encoding="utf-8")
    assert git(repo, "rev-parse", "HEAD") in recorded
    assert REPORT in recorded
    assert run_hook(repo, "git push").returncode == 0


@pytest.mark.parametrize("name", ["a.txt", "new.txt"])
def test_stamp_refuses_a_dirty_tree(
    repo: Path, report: Path, name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / name).write_text("changed\n", encoding="utf-8")

    assert gate.stamp(repo, report, [PASS]) == 1
    assert not stamp_of_head(repo).exists()
    assert "Arbre de travail modifié" in capsys.readouterr().err


def test_stamp_refuses_a_report_with_an_empty_section(
    repo: Path, report: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report.write_text(REPORT.replace("Aucune.\n", ""), encoding="utf-8")

    assert gate.stamp(repo, report, [PASS]) == 1
    assert not stamp_of_head(repo).exists()
    assert "Corrections" in capsys.readouterr().err


def test_stamp_refuses_when_a_check_fails(repo: Path, report: Path) -> None:
    assert gate.stamp(repo, report, [PASS, FAIL]) == 1
    assert not stamp_of_head(repo).exists()


def test_stamp_refuses_when_head_moves_during_the_checks(repo: Path, report: Path) -> None:
    checked = git(repo, "rev-parse", "HEAD")

    assert gate.stamp(repo, report, [COMMITS]) == 1
    assert git(repo, "rev-parse", "HEAD") != checked
    assert not list((repo / ".git").glob("dvb-review/*.md"))


def test_checks_are_the_uv_steps_of_the_ci() -> None:
    ci_commands = re.findall(r"^\s*- run: (uv run .+)$", CI_WORKFLOW.read_text(), re.MULTILINE)

    assert ci_commands
    assert [" ".join(check) for check in gate.CHECKS] == ci_commands
