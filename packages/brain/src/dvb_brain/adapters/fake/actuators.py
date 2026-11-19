"""Actuator board of the tests: fixed durations and a failure rate, reproducible by a seed.

The fake knows the actuators and sensors it is given, not the position names: the real adapter
reads them in robot.json. The state is computed from the Clock, so an actuator whose command
was given up still reaches its position (ADR 0011).
"""

import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from dvb_brain.domain.actuators import ActuatorResult, ActuatorState
from dvb_brain.ports.clock import Clock
from dvb_brain.ports.watch import Watch


@dataclass(frozen=True, slots=True)
class _Move:
    position_name: str | None  # None: stopped short of any named position
    end: float  # s, on the Clock
    result: ActuatorResult  # DONE or BLOCKED, once over


class FakeActuators:
    def __init__(
        self,
        clock: Clock,
        *,
        durations: Mapping[str, float],
        sensors: Iterable[str],
        failure_rate: float = 0.0,
        seed: int = 0,
    ) -> None:
        self._clock = clock
        self._durations = dict(durations)  # s, of any command, by actuator
        self._sensors = {name: Watch[bool](clock) for name in sensors}
        self._failure_rate = failure_rate
        self._random = random.Random(seed)
        self._moves: dict[str, _Move] = {}
        self._waiting: set[str] = set()
        self._released_for_good = False
        self.releases: list[tuple[float, bool]] = []  # (time, final) of each release_all

    async def command(
        self,
        actuator_id: str,
        position_name: str,
        timeout: float,  # noqa: ASYNC109 (counted on the Clock, see ActuatorPort)
    ) -> ActuatorResult:
        duration = self._duration(actuator_id)
        if self._released_for_good:
            raise RuntimeError("actuators released for good: no command after the end")
        if actuator_id in self._waiting:
            raise RuntimeError(f"another command of {actuator_id} is still waiting")
        failed = self._random.random() < self._failure_rate
        result = ActuatorResult.BLOCKED if failed else ActuatorResult.DONE
        move = _Move(position_name, self._clock.now() + duration, result)
        self._moves[actuator_id] = move
        self._waiting.add(actuator_id)
        try:
            await self._clock.sleep(min(duration, timeout))
        finally:
            self._waiting.discard(actuator_id)
        if self._moves.get(actuator_id) is not move:  # released meanwhile
            return ActuatorResult.BLOCKED
        if duration > timeout:  # the board gives up and stops where it is
            self._moves[actuator_id] = _Move(None, self._clock.now(), ActuatorResult.BLOCKED)
            return ActuatorResult.TIMEOUT
        # Over at the time the clock woke this task, a hair off the float deadline (ADR 0010).
        self._moves[actuator_id] = _Move(position_name, self._clock.now(), result)
        return result

    async def release_all(self, final: bool) -> None:
        if final:
            self._released_for_good = True
        self._moves.clear()
        self.releases.append((self._clock.now(), final))

    def state(self, actuator_id: str) -> ActuatorState:
        self._duration(actuator_id)
        move = self._moves.get(actuator_id)
        if move is None:
            return ActuatorState(position_name=None, moving=False)
        if self._clock.now() < move.end:
            return ActuatorState(position_name=None, moving=True)
        reached = move.position_name if move.result is ActuatorResult.DONE else None
        return ActuatorState(position_name=reached, moving=False)

    def sensor(self, name: str) -> Watch[bool]:
        if name not in self._sensors:
            raise ValueError(f"unknown sensor: {name}")
        return self._sensors[name]

    def _duration(self, actuator_id: str) -> float:
        if actuator_id not in self._durations:
            raise ValueError(f"unknown actuator: {actuator_id}")
        return self._durations[actuator_id]
