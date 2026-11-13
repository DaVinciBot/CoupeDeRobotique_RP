"""Scoring table of an edition: points of each scoring item and phases of the match.

Each edition gives its scoring table in its own scoring.json (ADR 0005): no point is written in
the code. This module only reads the points; how items combine (per unit, exclusive items,
additional points) is the business of the edition.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal

import msgspec

from dvb_brain.domain.decoding import Id, NonNegative, SchemaError, check_unique_ids, decode_json


@dataclass(frozen=True, slots=True, eq=False)
class Scoring:
    """parse_scoring gives read-only mappings. Equal only to itself, like Arena."""

    points: Mapping[str, int]  # by scoring item id, in file order
    phase_starts: Mapping[str, float]  # match time at which each phase starts, in s, by id


def parse_scoring(data: bytes) -> Scoring:
    """Decode the content of a scoring.json file.

    Raise a SchemaError that names the field and the value.
    """
    raw = decode_json(data, _ScoringFile)
    check_unique_ids("items", (item.id for item in raw.items))
    check_unique_ids("phases", (phase.id for phase in raw.phases))
    return Scoring(
        points=MappingProxyType({item.id: item.points for item in raw.items}),
        phase_starts=MappingProxyType({phase.id: phase.start_s for phase in raw.phases}),
    )


def load_scoring(path: Path) -> Scoring:
    """Read a scoring.json file. At startup only: this blocks on the disk."""
    try:
        return parse_scoring(path.read_bytes())
    except SchemaError as error:
        raise SchemaError(f"{path}: {error}") from error


# Schema of scoring.json: times in s. Each entry cites its rule, for the review.


class _ItemFile(msgspec.Struct, forbid_unknown_fields=True):
    id: Id
    points: Annotated[int, msgspec.Meta(gt=0)]
    rule: Id


class _PhaseFile(msgspec.Struct, forbid_unknown_fields=True):
    """Phase from start_s to the end of the match."""

    id: Id
    start_s: NonNegative
    rule: Id


class _ScoringFile(msgspec.Struct, forbid_unknown_fields=True):
    schema_version: Literal[1]
    kind: Literal["cdr.scoring"]
    items: list[_ItemFile]
    phases: list[_PhaseFile]
