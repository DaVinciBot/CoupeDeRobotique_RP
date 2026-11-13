"""Checks of the 2027 scoring table against the rules (RJ E, RJ F)."""

from pathlib import Path

from dvb_brain.domain.match_constants import load_match_constants
from dvb_brain.domain.scoring import load_scoring

SCORING = Path(__file__).parents[1] / "scoring.json"
MATCH_CONFIG = Path(__file__).parents[3] / "config" / "match.json"


def test_points_follow_the_rules() -> None:
    assert load_scoring(SCORING).points == {
        # RJ E.1.c: per stone, then per construction.
        "stone_in_construction_zone": 1,
        "wall_built": 5,
        "tower_built": 5,
        "gate_built": 20,
        # RJ E.2.c: per level for the elevation.
        "grail_in_castle": 5,
        "grail_level": 5,
        # RJ E.3.c: one or the other.
        "robot_partly_in_end_zone": 5,
        "robot_fully_in_end_zone": 10,
        # RJ E.4.c: per moat; the 15 points come on top of the 5 (RG H.4).
        "moat_occupied": 5,
        "pami_attacks_pami": 5,
        "ball_in_opponent_castle": 5,
        "three_balls_in_opponent_castle": 15,
    }


def test_attack_phase_starts_at_85_s() -> None:
    # RJ E.4.b: from the 85th second to the end of the match.
    attack_start = load_scoring(SCORING).phase_starts["attack"]

    assert attack_start == 85.0
    assert attack_start < load_match_constants(MATCH_CONFIG).duration
