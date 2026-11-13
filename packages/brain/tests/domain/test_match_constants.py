import copy
from pathlib import Path
from typing import Any

import msgspec
import pytest

from dvb_brain.domain.json_schema import SchemaError
from dvb_brain.domain.match_constants import load_match_constants, parse_match_constants

MATCH_CONFIG = Path(__file__).parents[4] / "config" / "match.json"


def valid_document() -> dict[str, Any]:
    return {"schema_version": 1, "kind": "cdr.match", "duration_s": 90, "max_height_mm": 400}


def encode(document: dict[str, Any]) -> bytes:
    return msgspec.json.encode(document)


def test_parse_match_constants_converts_to_si() -> None:
    constants = parse_match_constants(encode(valid_document()))

    assert constants.duration == 90.0
    assert constants.max_height == pytest.approx(0.4)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", 2, "$.schema_version: Invalid enum value 2"),
        ("kind", "cdr.other", "$.kind: Invalid enum value 'cdr.other'"),
        ("duration_s", 0, "$.duration_s: Expected `float` > 0.0, got 0"),
        ("max_height_mm", -1, "$.max_height_mm: Expected `float` > 0.0, got -1"),
        ("colour", "red", "$: Object contains unknown field `colour`"),
    ],
)
def test_parse_match_constants_error_names_field_and_value(
    field: str, value: object, expected: str
) -> None:
    document = copy.deepcopy(valid_document())
    document[field] = value

    with pytest.raises(SchemaError) as error:
        parse_match_constants(encode(document))

    assert str(error.value) == expected


def test_load_match_constants_error_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "match.json"
    document = valid_document()
    del document["duration_s"]
    path.write_bytes(encode(document))

    with pytest.raises(SchemaError) as error:
        load_match_constants(path)

    assert str(error.value).startswith(f"{path}: $:")
    assert "duration_s" in str(error.value)


def test_config_follows_the_general_rules() -> None:
    constants = load_match_constants(MATCH_CONFIG)

    assert constants.duration == 100.0  # RG H.2
    assert constants.max_height == pytest.approx(0.35)  # RG F.3
