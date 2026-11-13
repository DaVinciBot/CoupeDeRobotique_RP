"""Reading of the data files, at startup only (ADR 0008): the domain decodes bytes, never a path."""

from collections.abc import Callable
from pathlib import Path

from dvb_brain.domain.decoding import SchemaError


def load_file[T](path: Path, parse: Callable[[bytes], T]) -> T:
    """Read the file at path and decode it with parse, e.g. load_file(path, parse_arena).

    This blocks on the disk. A SchemaError names the file, then the field and the value.
    """
    try:
        return parse(path.read_bytes())
    except SchemaError as error:
        raise SchemaError(f"{path}: {error}") from error
