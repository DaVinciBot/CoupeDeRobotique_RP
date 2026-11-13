"""Checks of the 2027 strategies against the table, the actions and the rules (RG I.3.b)."""

from pathlib import Path

import pytest

from dvb_brain.app.files import load_file
from dvb_brain.domain.arena import Arena, Side, ZoneKind, parse_arena
from dvb_brain.domain.geometry import Vec2
from dvb_brain.domain.match_constants import MatchConstants, parse_match_constants
from dvb_brain.domain.strategy_model import (
    Strategy,
    check_strategy,
    mirror_strategy,
    parse_strategy,
)

EDITION = Path(__file__).parents[1]
STRATEGIES = sorted((EDITION / "strategies").glob("*.strategy.json"))
MATCH_CONFIG = EDITION.parents[1] / "config" / "match.json"

# Action types of TODO 7.1, until the edition registers its actions (TODO 7.1, ADR 0006).
ACTION_TYPES = frozenset(
    {"pick_stones", "build_wall", "build_tower", "build_gate", "raise_grail", "shoot_balls"}
)


@pytest.fixture(scope="module")
def arena() -> Arena:
    return load_file(EDITION / "arena.json", parse_arena)


@pytest.fixture(scope="module")
def match() -> MatchConstants:
    return load_file(MATCH_CONFIG, parse_match_constants)


def check(strategy: Strategy, arena: Arena, match: MatchConstants) -> None:
    check_strategy(
        strategy,
        arena=arena,
        arena_id="cdr_2027",
        action_types=ACTION_TYPES,
        match_duration=match.duration,
    )


def in_zone_of(arena: Arena, kind: ZoneKind, side: Side, point: Vec2) -> bool:
    return any(arena.contains(zone.id, point) for zone in arena.zones_of(kind, side))


@pytest.mark.parametrize("path", STRATEGIES, ids=lambda path: path.name)
def test_strategy_passes_the_checks_on_both_sides(
    path: Path, arena: Arena, match: MatchConstants
) -> None:
    strategy = load_file(path, parse_strategy)

    check(strategy, arena, match)
    check(mirror_strategy(strategy, arena), arena, match)


@pytest.mark.parametrize("side", [Side.BLUE, Side.YELLOW])
def test_homologation_leaves_the_start_zone_does_an_action_and_comes_back(
    side: Side, arena: Arena
) -> None:
    # RG I.3.b: leave the start zone and validate at least one action.
    strategy = load_file(EDITION / "strategies" / "homologation.strategy.json", parse_strategy)
    if strategy.side is not side:
        strategy = mirror_strategy(strategy, arena)
    positions = [step.move.position for step in strategy.steps]

    assert in_zone_of(arena, ZoneKind.START, side, positions[0])
    assert not all(in_zone_of(arena, ZoneKind.START, side, p) for p in positions)
    assert any(step.actions for step in strategy.steps)
    assert in_zone_of(arena, ZoneKind.END, side, positions[-1])  # RJ E.3
