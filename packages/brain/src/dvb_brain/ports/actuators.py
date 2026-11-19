"""Actuator port: the actuator board, by the names of the config (architecture, section 10).

The adapter translates each name into an angle or a position from robot.json. The height limit
(RG F.3) is checked before the call: named positions above it are refused when the config is
loaded, and the zone rule of the year is in MatchRules (ADR 0011).
"""

from typing import Protocol

from dvb_brain.domain.actuators import ActuatorResult, ActuatorState
from dvb_brain.ports.watch import Watch


class ActuatorPort(Protocol):
    # ASYNC109 advises asyncio.timeout, which counts on the event loop clock: the timeout of a
    # command counts on the Clock port, so that a fake clock drives it.

    async def command(
        self,
        actuator_id: str,
        position_name: str,
        timeout: float,  # noqa: ASYNC109
    ) -> ActuatorResult:
        """Move an actuator to a named position and return how it ended.

        Return TIMEOUT at the latest timeout seconds after the call, counted on the Clock, even
        with a silent board. Raise RuntimeError when another command() on the same actuator is
        still waiting, or after release_all(final=True); ValueError for an unknown actuator or
        position. Different actuators move at the same time. Cancelling command() only gives
        up the wait: the actuator goes on to its position, and a new command replaces it.
        """
        ...

    async def release_all(self, final: bool) -> None:
        """Stop holding and powering every actuator, without waiting for the board.

        final=True (end of match, FAULT, end of run_brain) is final for this port: it is
        recorded before the first await, and every later command() raises RuntimeError
        (RG H.3). final=False lets the early end of match retract the actuators afterwards.
        Never raises, even with a dead link.
        """
        ...

    def state(self, actuator_id: str) -> ActuatorState:
        """Return the last named position reached, and whether the actuator moves."""
        ...

    def sensor(self, name: str) -> Watch[bool]:
        """Return the readings of a sensor of the board (a limit switch in a gripper...)."""
        ...
