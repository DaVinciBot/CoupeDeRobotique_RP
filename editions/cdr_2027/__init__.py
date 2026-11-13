"""Edition module of the Coupe de France de Robotique 2027 (Eurobot 2027 rules).

The brain calls load() at startup, through dvb_brain.app.edition.load_edition.
"""

from dataclasses import dataclass
from pathlib import Path

from dvb_brain.app.edition import Edition
from dvb_brain.domain.arena import Arena, load_arena
from dvb_brain.domain.match_rules import MatchRules
from dvb_brain.domain.scoring import Scoring, load_scoring

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
        id="cdr_2027",  # name of this folder
        arena=load_arena(_FOLDER / "arena.json"),
        scoring=load_scoring(_FOLDER / "scoring.json"),
    )
