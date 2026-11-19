"""Edition module template: copy this folder to start a new theme (see README.md).

The brain calls load() at startup, through dvb_brain.app.edition.load_edition.
"""

from dataclasses import dataclass
from pathlib import Path

from dvb_brain.app.edition import Edition
from dvb_brain.app.files import load_file
from dvb_brain.domain.arena import Arena, parse_arena
from dvb_brain.domain.match_rules import MatchRules
from dvb_brain.domain.scoring import Scoring, parse_scoring

from .rules import Rules

_FOLDER = Path(__file__).parent


@dataclass(frozen=True, slots=True)
class _Edition:
    id: str
    arena: Arena
    scoring: Scoring

    def rules(self) -> MatchRules:
        return Rules(self.arena)


def load() -> Edition:
    """Read the files of the edition. At startup only: this blocks on the disk."""
    return _Edition(
        id=_FOLDER.name,
        arena=load_file(_FOLDER / "arena.json", parse_arena),
        scoring=load_file(_FOLDER / "scoring.json", parse_scoring),
    )
