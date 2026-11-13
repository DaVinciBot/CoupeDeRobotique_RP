from pathlib import Path

import pytest

from dvb_brain.app.files import load_file
from dvb_brain.domain.decoding import SchemaError
from dvb_brain.domain.match_constants import parse_match_constants


def write(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "match.json"
    path.write_bytes(content)
    return path


def test_load_file_decodes_the_file(tmp_path: Path) -> None:
    content = b'{"schema_version": 1, "kind": "cdr.match", "duration_s": 100, "max_height_mm": 350}'
    path = write(tmp_path, content)

    assert load_file(path, parse_match_constants).duration == 100.0


def test_load_file_error_names_the_file_then_the_field(tmp_path: Path) -> None:
    content = b'{"schema_version": 1, "kind": "cdr.match", "duration_s": 0, "max_height_mm": 350}'
    path = write(tmp_path, content)

    with pytest.raises(SchemaError) as error:
        load_file(path, parse_match_constants)

    assert str(error.value).startswith(f"{path}: $.duration_s:")


def test_load_file_error_names_the_file_for_invalid_json(tmp_path: Path) -> None:
    path = write(tmp_path, b"{")

    with pytest.raises(SchemaError) as error:
        load_file(path, parse_match_constants)

    assert str(error.value).startswith(f"{path}: invalid JSON")


def test_load_file_lets_a_missing_file_through(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_file(tmp_path / "missing.json", parse_match_constants)
