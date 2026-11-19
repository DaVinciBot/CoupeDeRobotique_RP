"""Decoding of the data files, with errors that name the field and the value.

The schemas of the files (arena, scoring, strategy, match constants) share the field types and
the checks below.
"""

import re
from collections.abc import Iterable
from typing import Annotated, cast

import msgspec

# Field types of the schemas. Units are given by the field names (x_mm, duration_s).
Id = Annotated[str, msgspec.Meta(min_length=1)]
Positive = Annotated[float, msgspec.Meta(gt=0)]
NonNegative = Annotated[float, msgspec.Meta(ge=0)]


class SchemaError(ValueError):
    """A data file does not match its schema."""


def field_error(path: str, reason: str, value: object) -> SchemaError:
    """Build the error for the field at path, e.g. "$.zones[1].id: duplicate id, got 'a'"."""
    return SchemaError(f"{path}: {reason}, got {value!r}")


def check_unique_ids(collection: str, ids: Iterable[str]) -> None:
    """Raise a SchemaError naming the first id of $.<collection> that is already used."""
    seen: set[str] = set()
    for i, entry_id in enumerate(ids):
        if entry_id in seen:
            raise field_error(f"$.{collection}[{i}].id", "duplicate id", entry_id)
        seen.add(entry_id)


def decode_json[T](data: bytes, type_: type[T]) -> T:
    """Decode data into type_, or raise a SchemaError that names the field and the value."""
    try:
        return msgspec.json.decode(data, type=type_)
    except msgspec.ValidationError as error:
        message = str(error)
        at = _AT.search(message)
        reason = message[: at.start()] if at else message
        path = at["path"] if at else "$"
        if at and at["key"]:  # msgspec does not say which key
            raise SchemaError(f"{path}: invalid key: {reason}") from error
        reason = _GOT_TYPE.sub("", reason)  # the value itself says more than its type
        value = _value_at(data, path)
        # msgspec already names the missing or unknown field of an object, and the bad enum value.
        if value is _MISSING or isinstance(value, dict) or reason.startswith("Invalid enum"):
            raise SchemaError(f"{path}: {reason}") from error
        raise field_error(path, reason, value) from error
    except msgspec.DecodeError as error:
        raise SchemaError(f"invalid JSON: {error}") from error


_MISSING = object()
# Where msgspec locates the error: " - at `$.zones[0].id`", or " - at `key` in `$.tags`".
_AT = re.compile(r" - at (?P<key>`key` in )?`(?P<path>[^`]*)`$")
_GOT_TYPE = re.compile(r", got `\w+`$")
_PATH = re.compile(r"\$(?:\.\w+|\[\d+\])*")
_STEP = re.compile(r"\.(\w+)|\[(\d+)\]")


def _value_at(data: bytes, path: str) -> object:
    """Return the value at a msgspec path such as $.zones[0].id, or _MISSING."""
    if not _PATH.fullmatch(path):
        return _MISSING
    try:
        node: object = msgspec.json.decode(data)
    except msgspec.DecodeError:
        return _MISSING
    for key, index in _STEP.findall(path):
        if key and isinstance(node, dict):
            node = cast(dict[str, object], node).get(key, _MISSING)
        elif index and isinstance(node, list) and int(index) < len(cast(list[object], node)):
            node = cast(list[object], node)[int(index)]
        else:
            return _MISSING
    return node
