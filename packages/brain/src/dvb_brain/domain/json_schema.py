"""JSON decoding with errors that name the field and the value."""

import re
from typing import cast

import msgspec


class SchemaError(ValueError):
    """A data file does not match its schema."""


def field_error(path: str, reason: str, value: object) -> SchemaError:
    """Build the error for the field at path, e.g. "$.zones[1].id: duplicate id, got 'a'"."""
    return SchemaError(f"{path}: {reason}, got {value!r}")


def decode_json[T](data: bytes, type_: type[T]) -> T:
    """Decode data into type_, or raise a SchemaError that names the field and the value."""
    try:
        return msgspec.json.decode(data, type=type_)
    except msgspec.ValidationError as error:
        reason, _, at = str(error).partition(" - at `")
        reason = _GOT_TYPE.sub("", reason)  # the value itself says more than its type
        path = at.removesuffix("`") or "$"
        value = _value_at(data, path)
        # msgspec already names the missing or unknown field of an object, and the bad enum value.
        if value is _MISSING or isinstance(value, dict) or reason.startswith("Invalid enum"):
            raise SchemaError(f"{path}: {reason}") from error
        raise field_error(path, reason, value) from error
    except msgspec.DecodeError as error:
        raise SchemaError(f"invalid JSON: {error}") from error


_MISSING = object()
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
