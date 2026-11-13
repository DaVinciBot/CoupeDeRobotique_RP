"""Scoring table of an edition: points of each scoring item and phases of the match.

Each edition gives its scoring table in its own scoring.json (ADR 0005): no point is written in
the code. This module only reads the points; how items combine (per unit, exclusive items,
additional points) is the business of the edition.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import msgspec

from dvb_brain.domain.json_schema import SchemaError, decode_json, field_error


@dataclass(frozen=True, slots=True)
class Scoring:
    points: Mapping[str, int]  # by scoring item id, in file order
    phase_starts: Mapping[str, float]  # match time at which each phase starts, in s, by id


def parse_scoring(data: bytes) -> Scoring:
    """Decode the content of a scoring.json file.

    Raise a SchemaError that names the field and the value.
    """
    raw = decode_json(data, _ScoringFile)
    _check_unique_ids("items", [item.id for item in raw.items])
    _check_unique_ids("phases", [phase.id for phase in raw.phases])
    return Scoring(
        points={item.id: item.points for item in raw.items},
        phase_starts={phase.id: phase.start_s for phase in raw.phases},
    )


def load_scoring(path: Path) -> Scoring:
    """Read a scoring.json file. At startup only: this blocks on the disk."""
    try:
        return parse_scoring(path.read_bytes())
    except SchemaError as error:
        raise SchemaError(f"{path}: {error}") from error


# Schema of scoring.json: times in s. Each entry cites its rule, for the review.

_Id = Annotated[str, msgspec.Meta(min_length=1)]


class _ItemFile(msgspec.Struct, forbid_unknown_fields=True):
    id: _Id
    points: Annotated[int, msgspec.Meta(gt=0)]
    rule: _Id


class _PhaseFile(msgspec.Struct, forbid_unknown_fields=True):
    """Phase from start_s to the end of the match."""

    id: _Id
    start_s: Annotated[float, msgspec.Meta(ge=0)]
    rule: _Id


class _ScoringFile(msgspec.Struct, forbid_unknown_fields=True):
    schema_version: Literal[1]
    kind: Literal["cdr.scoring"]
    items: list[_ItemFile]
    phases: list[_PhaseFile]


def _check_unique_ids(collection: str, ids: list[str]) -> None:
    seen: set[str] = set()
    for i, entry_id in enumerate(ids):
        if entry_id in seen:
            raise field_error(f"$.{collection}[{i}].id", "duplicate id", entry_id)
        seen.add(entry_id)
