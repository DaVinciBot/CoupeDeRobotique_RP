"""Constants of the general rules that hold for every edition, in SI units.

They are read from config/match.json (ADR 0005). The timing rules of the year, such as the
phases of a match, belong to the edition (domain/scoring.py).
"""

from dataclasses import dataclass
from typing import Literal

import msgspec

from dvb_brain.domain.decoding import Positive, decode_json
from dvb_brain.domain.units import mm_to_m


@dataclass(frozen=True, slots=True)
class MatchConstants:
    duration: float  # s, from the start cord to the end of the match (RG H.2)
    max_height: float  # m, robot and handled objects, at any time (RG F.3)


def parse_match_constants(data: bytes) -> MatchConstants:
    """Decode the content of a match.json file and convert it to SI.

    Raise a SchemaError that names the field and the value.
    """
    raw = decode_json(data, _MatchFile)
    return MatchConstants(duration=raw.duration_s, max_height=mm_to_m(raw.max_height_mm))


# Schema of match.json: lengths in mm, times in s.


class _MatchFile(msgspec.Struct, forbid_unknown_fields=True):
    schema_version: Literal[1]
    kind: Literal["cdr.match"]
    duration_s: Positive
    max_height_mm: Positive
