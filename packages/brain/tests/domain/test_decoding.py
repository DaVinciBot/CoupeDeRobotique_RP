from typing import Annotated

import msgspec
import pytest

from dvb_brain.domain.decoding import Id, Positive, SchemaError, check_unique_ids, decode_json


class _File(msgspec.Struct, forbid_unknown_fields=True):
    width_mm: Positive
    tags: dict[Id, Annotated[int, msgspec.Meta(ge=0)]] = {}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b'{"width_mm": "x"}', "$.width_mm: Expected `float`, got 'x'"),
        (b'{"width_mm": 0}', "$.width_mm: Expected `float` > 0.0, got 0"),
        (b'{"width_mm": 1, "extra": 2}', "$: Object contains unknown field `extra`"),
        (b"{}", "$: Object missing required field `width_mm`"),
        # The JSON is cut after the bad value: the value cannot be read again.
        (b'{"width_mm": 0, "tags": {}', "$.width_mm: Expected `float` > 0.0"),
        # msgspec gives no index for a value of a dict.
        (b'{"width_mm": 1, "tags": {"a": -1}}', "$.tags[...]: Expected `int` >= 0"),
        (b'{"width_mm": 1, "tags": {"": 1}}', "$.tags: invalid key: Expected `str` of length >= 1"),
    ],
)
def test_decode_json_error_names_the_field(data: bytes, expected: str) -> None:
    with pytest.raises(SchemaError) as error:
        decode_json(data, _File)

    assert str(error.value) == expected


def test_decode_json_rejects_invalid_json() -> None:
    with pytest.raises(SchemaError, match=r"^invalid JSON: "):
        decode_json(b'{"width_mm": 1', _File)


def test_check_unique_ids_names_the_second_entry() -> None:
    with pytest.raises(SchemaError) as error:
        check_unique_ids("zones", (zone_id for zone_id in ["a", "b", "a"]))

    assert str(error.value) == "$.zones[2].id: duplicate id, got 'a'"


def test_check_unique_ids_accepts_unique_ids() -> None:
    check_unique_ids("zones", ["a", "b"])
