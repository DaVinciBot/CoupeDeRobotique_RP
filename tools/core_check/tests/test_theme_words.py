import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "theme_words.py"


def run(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, paths)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_theme_word_is_reported_with_file_and_line(tmp_path: Path) -> None:
    source = tmp_path / "actions.py"
    source.write_text("x = 1\ndef pickStones() -> None: ...\n", encoding="utf-8")

    result = run(source)

    assert result.returncode == 1
    assert f'{source}:2: theme word "stone"' in result.stdout


def test_accented_word_is_reported(tmp_path: Path) -> None:
    labels = tmp_path / "labels.ts"
    labels.write_text('const title = "Château";\n', encoding="utf-8")

    result = run(labels)

    assert result.returncode == 1
    assert 'theme word "chateau"' in result.stdout


def test_generic_words_pass(tmp_path: Path) -> None:
    source = tmp_path / "navigator.py"
    source.write_text("def recalibrate(wall: str, gate: str) -> None: ...\n", encoding="utf-8")

    assert run(source).returncode == 0


def test_binary_file_is_skipped(tmp_path: Path) -> None:
    blob = tmp_path / "image.bin"
    blob.write_bytes(b"\xff\xfe stone \x00")

    assert run(blob).returncode == 0
