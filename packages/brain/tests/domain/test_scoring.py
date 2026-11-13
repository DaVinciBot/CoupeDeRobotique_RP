import copy
from pathlib import Path
from typing import Any

import msgspec
import pytest

from dvb_brain.domain.json_schema import SchemaError
from dvb_brain.domain.scoring import load_scoring, parse_scoring

TEMPLATE_SCORING = Path(__file__).parents[4] / "editions" / "_template" / "scoring.json"


def valid_document() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "cdr.scoring",
        "items": [
            {"id": "crate_delivered", "points": 3, "rule": "RJ X.1"},
            {"id": "robot_parked", "points": 10, "rule": "RJ X.2"},
        ],
        "phases": [{"id": "final", "start_s": 70, "rule": "RJ X.3"}],
    }


def encode(document: dict[str, Any]) -> bytes:
    return msgspec.json.encode(document)


def test_parse_scoring_reads_points_and_phases() -> None:
    scoring = parse_scoring(encode(valid_document()))

    assert scoring.points == {"crate_delivered": 3, "robot_parked": 10}
    assert list(scoring.points) == ["crate_delivered", "robot_parked"]  # file order
    assert scoring.phase_starts == {"final": 70.0}


DELETE = object()


@pytest.mark.parametrize(
    ("location", "value", "expected"),
    [
        (("schema_version",), 2, ["$.schema_version: Invalid enum value 2"]),
        (("kind",), "cdr.strategy", ["$.kind: Invalid enum value 'cdr.strategy'"]),
        (("items", 0, "points"), 0, ["$.items[0].points: Expected `int` >= 1, got 0"]),
        (("items", 0, "points"), 1.5, ["$.items[0].points: Expected `int`, got 1.5"]),
        (("items", 1, "id"), "", ["$.items[1].id:", "got ''"]),
        (("items", 1, "id"), "crate_delivered", ["$.items[1].id: duplicate id"]),
        (("items", 0, "rule"), DELETE, ["$.items[0]:", "rule"]),
        (("phases", 0, "start_s"), -1, ["$.phases[0].start_s: Expected `float` >= 0.0"]),
        (("phases",), DELETE, ["$:", "phases"]),
        (("phases", 0, "end_s"), 100, ["$.phases[0]:", "end_s"]),
    ],
)
def test_parse_scoring_error_names_field_and_value(
    location: tuple[str | int, ...], value: object, expected: list[str]
) -> None:
    document = copy.deepcopy(valid_document())
    *parents, last = location
    node: Any = document
    for key in parents:
        node = node[key]
    if value is DELETE:
        del node[last]
    else:
        node[last] = value

    with pytest.raises(SchemaError) as error:
        parse_scoring(encode(document))

    for text in expected:
        assert text in str(error.value)


def test_parse_scoring_rejects_a_duplicate_phase() -> None:
    document = valid_document()
    document["phases"].append({"id": "final", "start_s": 80, "rule": "RJ X.4"})

    with pytest.raises(SchemaError, match=r"\$\.phases\[1\]\.id: duplicate id, got 'final'"):
        parse_scoring(encode(document))


def test_load_scoring_error_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "scoring.json"
    document = valid_document()
    document["items"][0]["points"] = -2
    path.write_bytes(encode(document))

    with pytest.raises(SchemaError) as error:
        load_scoring(path)

    assert str(error.value).startswith(f"{path}: $.items[0].points:")


def test_template_scoring_loads() -> None:
    scoring = load_scoring(TEMPLATE_SCORING)

    assert scoring.points == {}
    assert scoring.phase_starts == {}
