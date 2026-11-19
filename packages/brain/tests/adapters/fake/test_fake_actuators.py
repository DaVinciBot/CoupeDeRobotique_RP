import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from dvb_brain.adapters.fake.actuators import FakeActuators
from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.domain.actuators import ActuatorResult, ActuatorState
from dvb_brain.ports.actuators import ActuatorPort

# The tasks are checked after advance() instead of awaited: a broken fake fails an assertion
# instead of hanging the test.
pytestmark = pytest.mark.asyncio

DURATIONS = {"gripper": 0.5, "lift": 1.0}
SENSORS = ("gripper_loaded",)


def make(clock: FakeClock, failure_rate: float = 0.0, seed: int = 0) -> FakeActuators:
    return FakeActuators(
        clock, durations=DURATIONS, sensors=SENSORS, failure_rate=failure_rate, seed=seed
    )


async def assert_refused(clock: FakeClock, call: Coroutine[Any, Any, object]) -> None:
    """Check that the call raises RuntimeError at once: a call that waits fails, not hangs."""
    task = asyncio.create_task(call)
    await clock.advance(0)
    if not task.done():
        task.cancel()
        pytest.fail("the call waits instead of being refused")
    assert isinstance(task.exception(), RuntimeError)


async def test_command_is_done_after_the_duration_of_the_actuator() -> None:
    clock = FakeClock()
    actuators: ActuatorPort = make(clock)
    assert actuators.state("gripper") == ActuatorState(position_name=None, moving=False)

    task = asyncio.create_task(actuators.command("gripper", "closed", timeout=2.0))
    await clock.advance(0.4)
    assert not task.done()
    assert actuators.state("gripper") == ActuatorState(position_name=None, moving=True)

    await clock.advance(0.1)

    assert task.result() is ActuatorResult.DONE
    assert actuators.state("gripper") == ActuatorState(position_name="closed", moving=False)


async def test_command_times_out_at_its_timeout_and_the_actuator_stops() -> None:
    clock = FakeClock()
    actuators = make(clock)

    task = asyncio.create_task(actuators.command("lift", "level_2", timeout=0.3))
    await clock.advance(0.3)

    assert task.result() is ActuatorResult.TIMEOUT
    await clock.advance(1.0)
    assert actuators.state("lift") == ActuatorState(position_name=None, moving=False)


async def test_failures_end_blocked_at_the_end_of_the_duration() -> None:
    clock = FakeClock()
    actuators = make(clock, failure_rate=1.0)

    task = asyncio.create_task(actuators.command("gripper", "closed", timeout=2.0))
    await clock.advance(0.5)

    assert task.result() is ActuatorResult.BLOCKED
    assert actuators.state("gripper") == ActuatorState(position_name=None, moving=False)


async def test_failures_follow_the_seed() -> None:
    async def results(seed: int) -> list[ActuatorResult]:
        clock = FakeClock()
        actuators = make(clock, failure_rate=0.5, seed=seed)
        out: list[ActuatorResult] = []
        for _ in range(20):
            task = asyncio.create_task(actuators.command("gripper", "closed", timeout=2.0))
            await clock.advance(0.5)
            out.append(task.result())
        return out

    first = await results(seed=7)

    assert first == await results(seed=7)
    assert set(first) == {ActuatorResult.DONE, ActuatorResult.BLOCKED}


async def test_a_second_waiting_command_on_the_same_actuator_is_refused() -> None:
    clock = FakeClock()
    actuators = make(clock)
    first = asyncio.create_task(actuators.command("gripper", "closed", timeout=2.0))
    await clock.advance(0)

    await assert_refused(clock, actuators.command("gripper", "open", timeout=2.0))

    await clock.advance(0.5)
    assert first.result() is ActuatorResult.DONE


async def test_different_actuators_move_at_the_same_time() -> None:
    clock = FakeClock()
    actuators = make(clock)

    gripper = asyncio.create_task(actuators.command("gripper", "closed", timeout=2.0))
    lift = asyncio.create_task(actuators.command("lift", "level_2", timeout=2.0))
    await clock.advance(1.0)

    assert gripper.result() is ActuatorResult.DONE
    assert lift.result() is ActuatorResult.DONE


async def test_a_cancelled_command_still_reaches_its_position() -> None:
    clock = FakeClock()
    actuators = make(clock)
    task = asyncio.create_task(actuators.command("lift", "level_2", timeout=2.0))
    await clock.advance(0.2)

    task.cancel()
    await clock.advance(0.6)
    assert actuators.state("lift") == ActuatorState(position_name=None, moving=True)

    await clock.advance(0.2)  # the lift started at 0 s for 1 s

    assert task.cancelled()
    assert actuators.state("lift") == ActuatorState(position_name="level_2", moving=False)


async def test_a_new_command_replaces_a_cancelled_one() -> None:
    clock = FakeClock()
    actuators = make(clock)
    task = asyncio.create_task(actuators.command("lift", "level_2", timeout=2.0))
    await clock.advance(0.2)
    task.cancel()
    await clock.advance(0)

    retract = asyncio.create_task(actuators.command("lift", "low", timeout=2.0))
    await clock.advance(1.0)

    assert retract.result() is ActuatorResult.DONE
    assert actuators.state("lift") == ActuatorState(position_name="low", moving=False)


async def test_release_all_lets_go_of_everything_and_ends_waiting_commands_blocked() -> None:
    clock = FakeClock()
    fake = make(clock)
    actuators: ActuatorPort = fake
    done = asyncio.create_task(actuators.command("gripper", "closed", timeout=2.0))
    await clock.advance(0.5)
    waiting = asyncio.create_task(actuators.command("lift", "level_2", timeout=2.0))
    await clock.advance(0.2)

    await actuators.release_all(final=False)
    await clock.advance(1.0)

    assert done.result() is ActuatorResult.DONE
    assert waiting.result() is ActuatorResult.BLOCKED
    assert actuators.state("gripper") == ActuatorState(position_name=None, moving=False)
    assert actuators.state("lift") == ActuatorState(position_name=None, moving=False)
    assert fake.releases == [(0.7, False)]


async def test_commands_go_on_after_a_release_that_is_not_final() -> None:
    clock = FakeClock()
    actuators = make(clock)
    await actuators.release_all(final=False)

    task = asyncio.create_task(actuators.command("lift", "low", timeout=2.0))
    await clock.advance(1.0)

    assert task.result() is ActuatorResult.DONE


async def test_a_final_release_refuses_every_later_command() -> None:
    clock = FakeClock()
    actuators = make(clock)

    await actuators.release_all(final=True)

    await assert_refused(clock, actuators.command("gripper", "open", timeout=2.0))


async def test_a_final_release_is_recorded_before_its_first_await() -> None:
    clock = FakeClock()
    actuators = make(clock)

    release = asyncio.create_task(actuators.release_all(final=True))
    await asyncio.sleep(0)  # the release starts, and may not be over

    await assert_refused(clock, actuators.command("gripper", "open", timeout=2.0))
    await clock.advance(0)
    assert release.done()


async def test_unknown_names_are_refused() -> None:
    actuators = make(FakeClock())

    with pytest.raises(ValueError, match="arm"):
        await actuators.command("arm", "up", timeout=1.0)
    with pytest.raises(ValueError, match="arm"):
        actuators.state("arm")
    with pytest.raises(ValueError, match="door_open"):
        actuators.sensor("door_open")


async def test_sensors_give_what_the_test_sets() -> None:
    actuators = make(FakeClock())
    sensor = actuators.sensor("gripper_loaded")
    assert sensor.get() is None

    sensor.set(True)

    assert actuators.sensor("gripper_loaded").get() is True
