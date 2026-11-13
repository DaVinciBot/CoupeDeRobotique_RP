import subprocess
import sys
from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    ("line", "word"),
    [
        ('label = "Écuries"', "ecurie"),
        ("camelot_gate = 1", "camelot"),
        ("king_arthur = 1", "arthur"),
        ('name = "Chevalier"', "chevalier"),
        ("knight_count = 2", "knight"),
    ],
)
def test_words_of_the_2027_theme_are_reported(tmp_path: Path, line: str, word: str) -> None:
    source = tmp_path / "labels.py"
    source.write_text(line + "\n", encoding="utf-8")

    result = run(source)

    assert result.returncode == 1
    assert f'theme word "{word}"' in result.stdout


def test_generic_words_pass(tmp_path: Path) -> None:
    source = tmp_path / "navigator.py"
    source.write_text("def recalibrate(wall: str, gate: str) -> None: ...\n", encoding="utf-8")

    assert run(source).returncode == 0


def test_binary_file_is_skipped(tmp_path: Path) -> None:
    blob = tmp_path / "image.bin"
    blob.write_bytes(b"\xff\xfe stone \x00")

    assert run(blob).returncode == 0
