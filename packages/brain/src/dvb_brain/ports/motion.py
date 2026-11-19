"""Motion port: the rolling base, seen from the brain.

The contract below holds for every adapter (Teensy, simulation, fake hardware); it follows the
motor board contract (ADR 0003) and is described in ADR 0010. A lost link, a silent board, a
restart (boot_id) or the emergency stop are watched by the SafetyMonitor, not by the callers of
this port.
"""

from typing import Protocol

from dvb_brain.domain.geometry import Pose
from dvb_brain.domain.motion import MotionStatus, MoveCommand, StopMode
from dvb_brain.ports.watch import Watch


class MotionPort(Protocol):
    async def move(self, cmd: MoveCommand) -> MotionStatus:
        """Run one move and return the status that ends it: ARRIVED, BLOCKED or STOPPED.

        The port gives the move its move_id, never 0. One move at a time: calling move() while
        another one runs, or after stop(URGENT), raises RuntimeError. Cancelling move() stops
        the robot as stop(SMOOTH) does before the cancellation goes on: giving up the wait never
        leaves the robot moving. move() does not detect a lost link, nor a MOVE the board ignores
        (not configured, heartbeat lost, emergency stop, invalid command: ADR 0003); the caller
        bounds its wait on the Clock (ADR 0010).
        """
        ...

    async def stop(self, mode: StopMode) -> None:
        """Send the stop and return without waiting for the board.

        SMOOTH brakes at the MAX_ACCEL setting of the board (MAX_ANGULAR_ACCEL in a rotation),
        the deceleration the safety zone is computed with (architecture, section 8.4), whatever
        the max_accel of the move; it cuts the motors at once during a push (ADR 0003).
        URGENT is final for this port (end of match, FAULT): no motion command leaves afterwards,
        not even a later SMOOTH stop or the stop of a cancelled move(), so that nothing softens
        it (RG H.3). The port records it before its first await. heartbeat() goes on: its
        loss would make the board brake on its own, softly.

        Never raises, even with a dead link: the SafetyMonitor and the end of run_brain must not
        get stuck on it. The running move() returns STOPPED once the board reports it.
        """
        ...

    async def set_max_speed(self, max_speed: float) -> bool:
        """Change the max speed of the running GOTO, which goes on without stopping (ADR 0003).

        The port sends the GOTO again, same target and same move_id, with this max_speed: the
        board slows down (or speeds up) along the straight line. Only a GOTO: STRAIGHT and
        ROTATE_BY are relative, and sent again they would start over from the measured pose.
        Return False and send nothing when no GOTO runs, once stop() has been called during it,
        or after stop(URGENT): a stopped move never starts again. Never waits for the board, and
        raises only ValueError when max_speed <= 0, which the board would read as its own limit.
        """
        ...

    async def heartbeat(self) -> None:
        """Send one heartbeat and return without waiting for the board.

        The SafetyMonitor calls it at 20 Hz (ADR 0003), after stop(URGENT) too: without it, the
        board stops on its own after 200 ms. Never raises, even with a dead link.
        """
        ...

    async def reset_pose(self, pose: Pose) -> None:
        """Set the absolute pose of the robot, which must be still (start, calibration).

        Raise RuntimeError while a move runs, while the robot still brakes after a cancelled
        move, even before a status shows it (the caller waits for a new status that is not
        MOVING), or after stop(URGENT). Return once a status shows the new pose; the caller
        bounds its wait on the Clock.
        """
        ...

    def status(self) -> Watch[MotionStatus]:
        """Return the last status of the board, and the next ones."""
        ...

    def link_ok(self) -> bool:
        """Tell whether the link to the board is open (port opened, not in error)."""
        ...
