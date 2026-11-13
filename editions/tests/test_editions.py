"""Checks that every edition passes, whatever its theme (ADR 0006).

An edition copied from _template is checked here without writing a test.
"""

from pathlib import Path

import pytest
from shapely import Polygon, box

from dvb_brain.app.edition import Edition, load_edition
from dvb_brain.app.files import load_file
from dvb_brain.domain.arena import Arena, ElementSpec, Side, ZoneKind
from dvb_brain.domain.geometry import Vec2
from dvb_brain.domain.strategy_model import mirror_strategy, parse_strategy

EDITIONS = Path(__file__).parents[1]
NAMES = sorted(path.parent.name for path in EDITIONS.glob("*/__init__.py"))
TOLERANCE = 1e-9  # rounding of the mm to m conversion


@pytest.fixture(scope="module", params=NAMES)
def edition(request: pytest.FixtureRequest) -> Edition:
    return load_edition(request.param)


@pytest.fixture(params=[Side.BLUE, Side.YELLOW], ids=lambda side: side.value)
def side(request: pytest.FixtureRequest) -> Side:
    return request.param


def footprint(element: ElementSpec) -> Polygon:
    half_length, half_width = element.size.length / 2, element.size.width / 2
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    points = [element.pose.to_world(Vec2(u * half_length, v * half_width)) for u, v in corners]
    return Polygon([(p.x, p.y) for p in points])


def in_zone_of(arena: Arena, kind: ZoneKind, side: Side, point: Vec2) -> bool:
    return any(arena.contains(zone.id, point) for zone in arena.zones_of(kind, side))


def test_editions_are_found() -> None:
    assert "_template" in NAMES


@pytest.mark.parametrize("name", NAMES)
def test_edition_loads_with_a_symmetric_table(name: str) -> None:
    assert load_edition(name).id == name  # load_edition also checks the symmetry


def test_everything_is_on_the_table(edition: Edition) -> None:
    arena = edition.arena
    table = box(0.0, 0.0, arena.width, arena.depth).buffer(TOLERANCE)
    for zone in arena.zones.values():
        assert table.covers(zone.polygon), zone.id
    for element in arena.elements.values():
        assert table.covers(footprint(element)), element.id


def test_end_zones_are_never_in_the_opponent_areas(edition: Edition, side: Side) -> None:
    # RG H.4: entering an exclusive area of the opponent is a forfeit.
    for zone in edition.rules().end_zones(side):
        assert ZoneKind.END in zone.kinds, zone.id
        assert zone.owner in (side, None), zone.id


def test_homologation_leaves_the_start_zone_does_an_action_and_ends(
    edition: Edition, side: Side
) -> None:
    # RG I.3.b: leave the start zone and validate at least one action.
    path = EDITIONS / edition.id / "strategies" / "homologation.strategy.json"
    strategy = load_file(path, parse_strategy)
    if not strategy.steps:
        pytest.skip(f"{edition.id}: the homologation strategy has no step yet")
    arena = edition.arena
    if strategy.side is not side:
        strategy = mirror_strategy(strategy, arena)
    positions = [step.move.position for step in strategy.steps]
    end_zones = edition.rules().end_zones(side)

    assert in_zone_of(arena, ZoneKind.START, side, positions[0])
    assert not all(in_zone_of(arena, ZoneKind.START, side, p) for p in positions)
    assert any(step.actions for step in strategy.steps)
    assert any(arena.contains(zone.id, positions[-1]) for zone in end_zones)
