"""Loading of the 2027 edition and its game rules (RJ E.3)."""

import pytest

from dvb_brain.app.edition import load_edition
from dvb_brain.domain.arena import Side


def test_edition_loads() -> None:
    edition = load_edition("cdr_2027")

    assert edition.id == "cdr_2027"
    assert len(edition.arena.elements) == 30  # RJ D.4: the stones
    assert edition.scoring.phase_starts["attack"] == 85.0  # RJ E.4.b


@pytest.mark.parametrize("side", [Side.BLUE, Side.YELLOW])
def test_end_zone_is_the_throne_room_of_the_side(side: Side) -> None:
    # RJ E.3: the robot ends the match in its throne room.
    edition = load_edition("cdr_2027")

    assert edition.rules().end_zones(side) == (edition.arena.zone(f"{side.value}_throne_room"),)
