"""Motion port: the rolling base, seen from the brain.

The contract below holds for every adapter (Teensy, simulation, fake hardware), whatever the
wire protocol of the motor board (ADR 0003). A lost link, a silent board, a restart (boot_id)
or the emergency stop are watched by the SafetyMonitor, not by the callers of this port.
"""

from typing import Protocol

from dvb_brain.domain.geometry import Pose
from dvb_brain.domain.motion import MotionStatus, MoveCommand, StopMode
from dvb_brain.ports.watch import Watch


class MotionPort(Protocol):
    async def move(self, cmd: MoveCommand) -> MotionStatus:
        """Run one move and return the status that ends it: ARRIVED, BLOCKED or STOPPED.

        The port gives the move its move_id. One move at a time: calling move() while another
        one runs raises RuntimeError. Cancelling move() stops the robot as stop(SMOOTH) does
        before the cancellation goes on: giving up the wait never leaves the robot moving.
        move() does not detect a lost link; the caller bounds its wait by its own deadline.
        """
        ...

    async def stop(self, mode: StopMode) -> None:
        """Send the stop and return without waiting for the board.

        Never raises, even with a dead link: the SafetyMonitor and the end of run_brain must not
        get stuck on it. The running move() returns STOPPED once the board reports it.
        """
        ...

    async def reset_pose(self, pose: Pose) -> None:
        """Set the absolute pose of the robot, which must be still (start, calibration).

        Raise RuntimeError while a move runs. Return once a status shows the new pose.
        """
        ...

    def status(self) -> Watch[MotionStatus]:
        """Return the last status of the board, and the next ones."""
        ...

    def link_ok(self) -> bool:
        """Tell whether the link to the board is open (port opened, not in error)."""
        ...
