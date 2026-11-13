import copy
import math
from pathlib import Path
from typing import Any

import msgspec
import pytest
from hypothesis import given
from hypothesis import strategies as st

from dvb_brain.domain.arena import Arena, ElementSpec, Side, Size, load_arena
from dvb_brain.domain.geometry import Pose, Vec2, angle_diff
from dvb_brain.domain.json_schema import SchemaError
from dvb_brain.domain.strategy_model import (
    Abort,
    Action,
    GoTo,
    Move,
    MoveMode,
    Skip,
    Step,
    Strategy,
    Tolerance,
    check_strategy,
    load_strategy,
    mirror_strategy,
    parse_strategy,
)

EDITIONS = Path(__file__).parents[4] / "editions"
WIDTH = 3.0
DURATION = 100.0
ACTION_TYPES = frozenset({"grab", "release"})


def crate(element_id: str, x: float, mirror_id: str) -> ElementSpec:
    return ElementSpec(element_id, "crate", Pose(x, 1.6, 0.0), Size(0.2, 0.1, 0.05), mirror_id)


def make_arena() -> Arena:
    elements = [crate("crate_blue", 0.6, "crate_yellow"), crate("crate_yellow", 2.4, "crate_blue")]
    return Arena(
        width=WIDTH,
        depth=2.0,
        border_thickness=0.022,
        border_height=0.07,
        zones={},
        elements={element.id: element for element in elements},
        aruco_tags={Side.BLUE: frozenset({1}), Side.YELLOW: frozenset({6})},
    )


@pytest.fixture
def arena() -> Arena:
    return make_arena()


def valid_document() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "cdr.strategy",
        "name": "delivery",
        "arena_id": "test_arena",
        "side": "blue",
        "units": {"length": "mm", "angle": "deg", "time": "s", "speed": "m/s"},
        "end_reserve_s": 6,
        "steps": [
            {
                "id": "start",
                "label": "Start",
                "move": {"x_mm": 200, "y_mm": 300, "theta_deg": 0, "speed_mps": 0.5},
                "actions": [],
                "timeout_s": 0,
                "on_timeout": "skip",
            },
            {
                "id": "grab",
                "label": "Crate",
                "move": {
                    "x_mm": 600,
                    "y_mm": 1300,
                    "theta_deg": 90,
                    "speed_mps": 0.4,
                    "mode": "reverse",
                    "tolerance": {"position_mm": 15, "angle_deg": 2},
                },
                "actions": [
                    {
                        "type": "grab",
                        "actuator_id": "gripper",
                        "element_id": "crate_blue",
                        "duration_s": 2.5,
                        "score_delta": 3,
                    }
                ],
                "not_before_s": 30,
                "timeout_s": 10,
                "on_timeout": "goto:home",
            },
            {
                "id": "home",
                "label": "Back home",
                "move": {"x_mm": 200, "y_mm": 300, "speed_mps": 0.5, "mode": "auto"},
                "actions": [],
                "timeout_s": 0,
                "on_timeout": "abort",
            },
        ],
        "metadata": {"estimated_time_s": 25, "estimated_score": 3, "saved_at": "2026-11-13"},
    }


def encode(document: dict[str, Any]) -> bytes:
    return msgspec.json.encode(document)


def check(strategy: Strategy, arena: Arena) -> None:
    check_strategy(
        strategy,
        arena=arena,
        arena_id="test_arena",
        action_types=ACTION_TYPES,
        match_duration=DURATION,
    )


# Loading


def test_parse_strategy_reads_the_header() -> None:
    strategy = parse_strategy(encode(valid_document()))

    assert (strategy.name, strategy.arena_id, strategy.side) == (
        "delivery",
        "test_arena",
        Side.BLUE,
    )
    assert strategy.end_reserve == 6.0
    assert [step.id for step in strategy.steps] == ["start", "grab", "home"]


def test_parse_strategy_converts_a_move_to_si() -> None:
    move = parse_strategy(encode(valid_document())).steps[1].move

    assert (move.position.x, move.position.y) == pytest.approx((0.6, 1.3))
    assert move.theta == pytest.approx(math.pi / 2)
    assert move.max_speed == 0.4
    assert move.mode is MoveMode.REVERSE
    assert move.tolerance.position == pytest.approx(0.015)
    assert move.tolerance.angle == pytest.approx(math.radians(2))


def test_parse_strategy_fills_move_defaults() -> None:
    move = parse_strategy(encode(valid_document())).steps[0].move

    assert move.mode is MoveMode.FORWARD
    assert move.tolerance.position == pytest.approx(0.02)  # architecture, section 9.1
    assert move.tolerance.angle == pytest.approx(math.radians(3))


def test_parse_strategy_keeps_a_move_without_final_heading() -> None:
    move = parse_strategy(encode(valid_document())).steps[2].move

    assert move.theta is None
    assert move.mode is MoveMode.AUTO


def test_parse_strategy_normalizes_the_heading() -> None:
    document = valid_document()
    document["steps"][1]["move"]["theta_deg"] = 270

    move = parse_strategy(encode(document)).steps[1].move

    assert move.theta == pytest.approx(-math.pi / 2)


def test_parse_strategy_reads_actions_and_timing() -> None:
    step = parse_strategy(encode(valid_document())).steps[1]

    assert step.actions == (Action("grab", 2.5, "gripper", "crate_blue", 3),)
    assert step.not_before == 30.0
    assert step.timeout == 10.0


def test_parse_strategy_zero_timeout_means_no_limit() -> None:
    step = parse_strategy(encode(valid_document())).steps[0]

    assert step.timeout is None
    assert step.not_before is None


def test_parse_strategy_parses_on_timeout() -> None:
    steps = parse_strategy(encode(valid_document())).steps

    assert [step.on_timeout for step in steps] == [Skip(), GoTo("home"), Abort()]


def test_parse_strategy_editor_fields_are_optional() -> None:
    document = valid_document()
    del document["metadata"]
    del document["steps"][1]["actions"][0]["score_delta"]

    strategy = parse_strategy(encode(document))

    assert strategy.steps[1].actions[0].score_delta == 0


DELETE = object()


@pytest.mark.parametrize(
    ("location", "value", "expected"),
    [
        (("schema_version",), 2, ["$.schema_version: Invalid enum value 2"]),
        (("kind",), "cdr.scoring", ["$.kind: Invalid enum value 'cdr.scoring'"]),
        (("units", "length"), "cm", ["$.units.length: Invalid enum value 'cm'"]),
        (("units",), DELETE, ["$:", "units"]),
        (("side",), "green", ["$.side:", "'green'"]),
        (("name",), "", ["$.name:", "got ''"]),
        (("end_reserve_s",), -1, ["$.end_reserve_s: Expected `float` >= 0.0, got -1"]),
        (("steps", 1, "move", "speed_mps"), 0, ["$.steps[1].move.speed_mps:", "got 0"]),
        (("steps", 1, "move", "mode"), "sideways", ["$.steps[1].move.mode:", "'sideways'"]),
        (
            ("steps", 1, "move", "tolerance", "position_mm"),
            0,
            ["$.steps[1].move.tolerance.position_mm:", "got 0"],
        ),
        (("steps", 1, "move", "x_mm"), DELETE, ["$.steps[1].move:", "x_mm"]),
        (("steps", 1, "timeout_s"), -1, ["$.steps[1].timeout_s:", "got -1"]),
        (("steps", 1, "not_before_s"), -1, ["$.steps[1].not_before_s:", "got -1"]),
        (("steps", 1, "on_timeout"), DELETE, ["$.steps[1]:", "on_timeout"]),
        (("steps", 1, "actions", 0, "duration_s"), -1, ["$.steps[1].actions[0].duration_s:"]),
        (("steps", 1, "actions", 0, "type"), "", ["$.steps[1].actions[0].type:", "got ''"]),
        (("steps", 1, "actions", 0, "colour"), "red", ["$.steps[1].actions[0]:", "colour"]),
        (("steps", 2, "id"), "start", ["$.steps[2].id: duplicate id, got 'start'"]),
        (
            ("steps", 1, "on_timeout"),
            "jump",
            ["$.steps[1].on_timeout: expected skip, abort or goto:<step id>, got 'jump'"],
        ),
        (("steps", 1, "on_timeout"), "goto:", ["$.steps[1].on_timeout: expected skip"]),
        (("steps", 1, "on_timeout"), "skip:home", ["$.steps[1].on_timeout: expected skip"]),
        (
            ("steps", 1, "on_timeout"),
            "goto:nowhere",
            ["$.steps[1].on_timeout: no such step, got 'goto:nowhere'"],
        ),
        (("metadata", "estimated_score"), "high", ["$.metadata.estimated_score:", "'high'"]),
    ],
)
def test_parse_strategy_error_names_field_and_value(
    location: tuple[str | int, ...], value: object, expected: list[str]
) -> None:
    document = copy.deepcopy(valid_document())
    *parents, last = location
    node: Any = document
    for key in parents:
        node = node[key]
    if value is DELETE:
        del node[last]
    else:
        node[last] = value

    with pytest.raises(SchemaError) as error:
        parse_strategy(encode(document))

    for text in expected:
        assert text in str(error.value)


def test_load_strategy_error_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "delivery.strategy.json"
    document = valid_document()
    document["side"] = "red"
    path.write_bytes(encode(document))

    with pytest.raises(SchemaError) as error:
        load_strategy(path)

    assert str(error.value).startswith(f"{path}: $.side:")


# Checks against the table, the actions and the match


def test_check_strategy_accepts_a_valid_strategy(arena: Arena) -> None:
    check(parse_strategy(encode(valid_document())), arena)


def test_check_strategy_accepts_actions_until_the_end_of_the_match(arena: Arena) -> None:
    document = valid_document()
    document["steps"][1]["not_before_s"] = DURATION

    check(parse_strategy(encode(document)), arena)


@pytest.mark.parametrize(
    ("location", "value", "expected"),
    [
        (("arena_id",), "other_arena", "$.arena_id: expected 'test_arena', got 'other_arena'"),
        (
            ("steps", 1, "not_before_s"),
            100.5,
            "$.steps[1].not_before_s: after the end of the match at 100 s, got 100.5",
        ),
        (
            ("steps", 1, "actions", 0, "type"),
            "juggle",
            "$.steps[1].actions[0].type: unknown action type, got 'juggle'",
        ),
        (
            ("steps", 1, "actions", 0, "element_id"),
            "crate_green",
            "$.steps[1].actions[0].element_id: unknown element, got 'crate_green'",
        ),
    ],
)
def test_check_strategy_error_names_field_and_value(
    arena: Arena, location: tuple[str | int, ...], value: object, expected: str
) -> None:
    document = copy.deepcopy(valid_document())
    *parents, last = location
    node: Any = document
    for key in parents:
        node = node[key]
    node[last] = value
    strategy = parse_strategy(encode(document))

    with pytest.raises(SchemaError) as error:
        check(strategy, arena)

    assert str(error.value) == expected


# Symmetry


def test_mirror_strategy_changes_side_poses_and_elements(arena: Arena) -> None:
    mirrored = mirror_strategy(parse_strategy(encode(valid_document())), arena)

    assert mirrored.side is Side.YELLOW
    start, grab, home = mirrored.steps
    assert (start.move.position.x, start.move.position.y) == pytest.approx((2.8, 0.3))
    assert start.move.theta == pytest.approx(math.pi)
    assert (grab.move.position.x, grab.move.position.y) == pytest.approx((2.4, 1.3))
    assert grab.move.theta == pytest.approx(math.pi / 2)
    assert grab.actions[0].element_id == "crate_yellow"
    assert home.move.theta is None


def test_mirror_strategy_keeps_the_rest(arena: Arena) -> None:
    strategy = parse_strategy(encode(valid_document()))
    mirrored = mirror_strategy(strategy, arena)

    for step, mirror in zip(strategy.steps, mirrored.steps, strict=True):
        assert (mirror.id, mirror.label, mirror.on_timeout) == (
            step.id,
            step.label,
            step.on_timeout,
        )
        assert (mirror.not_before, mirror.timeout) == (step.not_before, step.timeout)
        assert (mirror.move.mode, mirror.move.tolerance) == (step.move.mode, step.move.tolerance)
        assert mirror.move.max_speed == step.move.max_speed
    assert (mirrored.name, mirrored.end_reserve) == (strategy.name, strategy.end_reserve)


def test_mirrored_strategy_passes_the_checks(arena: Arena) -> None:
    check(mirror_strategy(parse_strategy(encode(valid_document())), arena), arena)


headings = st.one_of(st.none(), st.floats(min_value=-math.pi, max_value=math.pi))
moves = st.builds(
    lambda x, y, theta: Move(
        Vec2(x, y), theta, 0.5, MoveMode.FORWARD, Tolerance(0.02, math.radians(3))
    ),
    st.floats(min_value=0.0, max_value=WIDTH),
    st.floats(min_value=0.0, max_value=2.0),
    headings,
)
element_ids = st.one_of(st.none(), st.sampled_from(["crate_blue", "crate_yellow"]))


@given(st.lists(st.tuples(moves, element_ids), max_size=5))
def test_mirror_strategy_twice_is_identity(steps: list[tuple[Move, str | None]]) -> None:
    table = make_arena()  # not the fixture: Hypothesis runs the test many times
    strategy = Strategy(
        name="random",
        arena_id="test_arena",
        side=Side.BLUE,
        end_reserve=5.0,
        steps=tuple(
            Step(
                id=f"s{i}",
                label="",
                move=move,
                actions=(Action("grab", 1.0, None, element_id, 0),),
                not_before=None,
                timeout=None,
                on_timeout=Skip(),
            )
            for i, (move, element_id) in enumerate(steps)
        ),
    )

    twice = mirror_strategy(mirror_strategy(strategy, table), table)

    assert twice.side is strategy.side
    for step, back in zip(strategy.steps, twice.steps, strict=True):
        assert back.move.position.x == pytest.approx(step.move.position.x, abs=1e-9)
        assert back.move.position.y == step.move.position.y
        if step.move.theta is None:
            assert back.move.theta is None
        else:
            assert back.move.theta is not None
            assert angle_diff(back.move.theta, step.move.theta) == pytest.approx(0.0, abs=1e-9)
        assert back.actions == step.actions


# Template


def test_template_strategy_loads_and_passes_the_checks() -> None:
    template = EDITIONS / "_template"
    strategy = load_strategy(template / "strategies" / "homologation.strategy.json")

    check_strategy(
        strategy,
        arena=load_arena(template / "arena.json"),
        arena_id="_template",
        action_types=frozenset(),
        match_duration=DURATION,
    )
    assert strategy.steps == ()
