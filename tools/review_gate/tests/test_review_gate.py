import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "review_gate.py"
REPO_ROOT = Path(__file__).parents[3]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"

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
    """No user or system git config, no GIT_* variable left by Claude Code or a git hook."""
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
def claude_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment that .claude/settings.json gives to Claude's commands: the pre-push hook."""
    for name, value in json.loads(SETTINGS.read_text(encoding="utf-8"))["env"].items():
        monkeypatch.setenv(name, value)


def require_config_hooks(repo: Path) -> None:
    """Skip on a git that ignores hooks declared in the config (before 2.54), but not in the CI."""
    if "dvb-review" in run_git(repo, "hook", "list", "pre-push").stdout.split():
        return
    reason = "this git ignores the hooks declared in its config (git 2.54 or newer needed)"
    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
def remote(repo: Path, tmp_path: Path, claude_env: None) -> Path:
    """A bare remote of a repository that holds this script, pushed to from Claude's commands."""
    path = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(path))
    git(repo, "remote", "add", "origin", str(path))
    (repo / "tools" / "review_gate").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "tools" / "review_gate" / "review_gate.py")
    git(repo, "add", "tools")
    git(repo, "commit", "-q", "-m", "build: add the review gate")
    require_config_hooks(repo)
    return path


@pytest.fixture
def report(tmp_path: Path) -> Path:
    path = tmp_path / "report.md"
    path.write_text(REPORT, encoding="utf-8")
    return path


def stamp_of(repo: Path, revision: str = "HEAD") -> Path:
    common = Path(repo, git(repo, "rev-parse", "--git-common-dir"))
    return common / "dvb-review" / f"{git(repo, 'rev-parse', revision)}.md"


def record_review(repo: Path, revision: str = "HEAD") -> None:
    path = stamp_of(repo, revision)
    path.parent.mkdir(exist_ok=True)
    path.write_text(REPORT, encoding="utf-8")


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)


def remote_branches(remote: Path) -> str:
    return git(remote, "for-each-ref", "--format=%(refname)", "refs/heads")


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


# Pre-push hook: it sees what git pushes, whatever the command that runs git.


@pytest.mark.parametrize(
    "args",
    [
        ("push", "-u", "origin", "feat/x"),
        ("push", "origin", "HEAD:refs/heads/other"),
        ("push", "--all", "origin"),
        ("-c", "alias.publish=push", "publish", "origin", "feat/x"),
    ],
)
def test_push_without_review_is_refused(repo: Path, remote: Path, args: tuple[str, ...]) -> None:
    result = run_git(repo, *args)

    assert result.returncode != 0
    assert "Revue manquante" in result.stderr
    assert git(repo, "rev-parse", "HEAD") in result.stderr
    assert remote_branches(remote) == ""


def test_push_of_a_reviewed_commit_passes(repo: Path, remote: Path, report: Path) -> None:
    assert gate.stamp(repo, report, [PASS]) == 0

    result = run_git(repo, "push", "-u", "origin", "feat/x")

    assert result.returncode == 0, result.stderr
    assert git(remote, "rev-parse", "feat/x") == git(repo, "rev-parse", "HEAD")


def test_review_of_head_does_not_cover_another_branch(repo: Path, remote: Path) -> None:
    git(repo, "switch", "-q", "-c", "other")
    commit(repo, "b.txt", "feat: add b")
    git(repo, "switch", "-q", "feat/x")
    record_review(repo)

    result = run_git(repo, "push", "origin", "feat/x", "other")

    assert result.returncode != 0
    assert git(repo, "rev-parse", "other") in result.stderr


def test_commit_made_after_the_review_is_refused(repo: Path, remote: Path) -> None:
    record_review(repo)
    commit(repo, "b.txt", "feat: add b")

    assert run_git(repo, "push", "origin", "feat/x").returncode != 0


def test_push_of_a_commit_signed_by_claude_is_refused(repo: Path, remote: Path) -> None:
    commit(repo, "b.txt", "feat: add b", SIGNED)
    record_review(repo)

    result = run_git(repo, "push", "origin", "feat/x")

    assert result.returncode != 0
    assert "Signature de Claude" in result.stderr


def test_branch_deletion_passes(repo: Path, remote: Path) -> None:
    record_review(repo)
    assert run_git(repo, "push", "origin", "feat/x").returncode == 0

    result = run_git(repo, "push", "origin", "--delete", "feat/x")

    assert result.returncode == 0, result.stderr
    assert remote_branches(remote) == ""


def test_review_is_shared_by_the_worktrees(repo: Path, remote: Path, tmp_path: Path) -> None:
    git(repo, "worktree", "add", "-q", "-b", "feat/y", str(tmp_path / "wt"))
    record_review(repo)

    assert run_git(tmp_path / "wt", "push", "origin", "feat/y").returncode == 0


@pytest.mark.parametrize("where", ["worktree", "subdirectory"])
def test_push_from_anywhere_in_the_clone_needs_a_review(
    repo: Path, remote: Path, tmp_path: Path, where: str
) -> None:
    if where == "worktree":
        git(repo, "worktree", "add", "-q", "-b", "feat/y", str(tmp_path / "wt"))
        cwd, branch = tmp_path / "wt", "feat/y"
    else:
        cwd, branch = repo / "tools", "feat/x"

    result = run_git(cwd, "push", "origin", branch)

    assert result.returncode != 0
    assert "Revue manquante" in result.stderr


def test_checkout_without_the_gate_is_refused(repo: Path, tmp_path: Path, claude_env: None) -> None:
    git(tmp_path, "init", "-q", "--bare", str(tmp_path / "remote.git"))
    git(repo, "remote", "add", "origin", str(tmp_path / "remote.git"))
    require_config_hooks(repo)

    result = run_git(repo, "push", "origin", "feat/x")

    assert result.returncode != 0
    assert "review_gate.py" in result.stderr


def test_pre_push_refuses_what_it_cannot_check(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "pre-push", "origin", "url"],
        cwd=tmp_path,
        input=f"refs/heads/x {'1' * 40} refs/heads/x {'0' * 40}\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "review_gate a échoué" in result.stderr


# PreToolUse hook on git and gh commands.


@pytest.mark.parametrize(
    "command", ["git push", "git push -u origin feat/x", "gh pr create --fill"]
)
def test_push_needs_the_pre_push_hook(repo: Path, command: str) -> None:
    result = run_hook(repo, command)

    assert result.returncode == 2
    assert "hook pre-push de revue n'est pas actif" in result.stderr


@pytest.mark.parametrize(
    "command", ["git push", "git push -u origin feat/x", "gh pr create --fill"]
)
def test_push_is_left_to_the_pre_push_hook(repo: Path, remote: Path, command: str) -> None:
    assert run_hook(repo, command).returncode == 0


@pytest.mark.parametrize("command", ["git push --no-verify", "git push origin x --no-verify -u"])
def test_push_without_the_pre_push_hook_is_refused(repo: Path, remote: Path, command: str) -> None:
    result = run_hook(repo, command)

    assert result.returncode == 2
    assert "--no-verify" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git log --oneline -5",
        "git commit -m 'docs: say why we push'",
        'git ls-files | xargs grep -n "git push"',
        "cat > deploy.sh <<'EOF'\necho it's\ngit push origin x\nEOF",
        "git diff && cat > doc.md <<'EOF'\n- `git push --no-verify` is refused, it's said\nEOF",
        'git commit -m "docs: never git push --no-verify"',
        "gh pr view 12",
        "gh pr merge 12 --squash",
        'git log origin/dev..HEAD --grep "Generated with Claude Code"',
        f"gh pr list --search '{SIGNED} in:body'",
    ],
)
def test_other_commands_pass(repo: Path, remote: Path, command: str) -> None:
    assert run_hook(repo, command).returncode == 0


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


def test_missing_body_file_is_left_to_gh(repo: Path, remote: Path) -> None:
    assert run_hook(repo, "gh pr create --title t --body-file missing.md").returncode == 0


def test_hook_refuses_what_it_cannot_check() -> None:
    result = run_tool({"tool_name": "Bash"})

    assert result.returncode == 2
    assert "review_gate a échoué" in result.stderr


# PreToolUse hook on the GitHub tools of the MCP servers.


@pytest.mark.parametrize(
    "tool",
    [
        "mcp__plugin_github_github__create_pull_request",
        "mcp__plugin_github_github__push_files",
        "mcp__claude_ai_GitHub__create_pr",
        "mcp__claude_ai_GitHub__create_or_update_file",
        "mcp__claude_ai_GitHub__delete_file",
    ],
)
def test_github_tools_that_publish_are_refused(tool: str) -> None:
    result = run_tool({"tool_name": tool, "tool_input": {"title": "feat: x"}})

    assert result.returncode == 2
    assert "sans passer par git push" in result.stderr


def test_github_tool_text_signed_by_claude_is_refused() -> None:
    body = {"title": "Bug", "body": f"Steps.\n\n{SIGNED}"}

    result = run_tool({"tool_name": "mcp__plugin_github_github__create_issue", "tool_input": body})

    assert result.returncode == 2
    assert "Signature de Claude" in result.stderr


@pytest.mark.parametrize(
    "tool", ["mcp__plugin_github_github__create_issue", "mcp__claude_ai_GitHub__merge_pr"]
)
def test_other_github_tools_pass(tool: str) -> None:
    body = {"title": "Bug", "body": "Steps.\n\nCo-Authored-By: Claude Dupont <c@example.com>"}

    assert run_tool({"tool_name": tool, "tool_input": body}).returncode == 0


# Stamp.


def test_stamp_records_the_report_for_head(repo: Path, report: Path) -> None:
    assert gate.stamp(repo, report, [PASS]) == 0

    recorded = stamp_of(repo).read_text(encoding="utf-8")
    assert git(repo, "rev-parse", "HEAD") in recorded
    assert REPORT in recorded


@pytest.mark.parametrize("name", ["a.txt", "new.txt"])
def test_stamp_refuses_a_dirty_tree(
    repo: Path, report: Path, name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / name).write_text("changed\n", encoding="utf-8")

    assert gate.stamp(repo, report, [PASS]) == 1
    assert not stamp_of(repo).exists()
    assert "Arbre de travail modifié" in capsys.readouterr().err


def test_stamp_refuses_a_report_with_an_empty_section(
    repo: Path, report: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report.write_text(REPORT.replace("Aucune.\n", ""), encoding="utf-8")

    assert gate.stamp(repo, report, [PASS]) == 1
    assert not stamp_of(repo).exists()
    assert "Corrections" in capsys.readouterr().err


def test_stamp_refuses_when_a_check_fails(repo: Path, report: Path) -> None:
    assert gate.stamp(repo, report, [PASS, FAIL]) == 1
    assert not stamp_of(repo).exists()


def test_stamp_refuses_when_head_moves_during_the_checks(repo: Path, report: Path) -> None:
    checked = git(repo, "rev-parse", "HEAD")

    assert gate.stamp(repo, report, [COMMITS]) == 1
    assert git(repo, "rev-parse", "HEAD") != checked
    assert not list((repo / ".git").glob("dvb-review/*.md"))


def test_checks_are_the_uv_steps_of_the_ci() -> None:
    # One-line steps, `run:` under a `name:`, and the lines of a `run: |` block alike.
    ci_commands = re.findall(
        r"^\s*(?:- )?(?:run: )?(uv run .+)$", CI_WORKFLOW.read_text(), re.MULTILINE
    )

    assert ci_commands
    assert [" ".join(check) for check in gate.CHECKS] == ci_commands
