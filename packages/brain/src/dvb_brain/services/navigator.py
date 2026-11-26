"""Navigator: takes the robot to a target of the strategy, or against a border (TODO 5.4).

It plans with the planner (5.2), runs the moves of motion_plan (5.3) one at a time and bounds
each wait on the Clock (ADR 0010). The pose comes from the motion port; the world model gives
the opponents, our constructions and the elements in place (ADR 0014).
"""

import math
from enum import StrEnum, auto

from dvb_brain.domain.arena import Arena, Side
from dvb_brain.domain.geometry import Pose
from dvb_brain.domain.match_rules import MatchRules
from dvb_brain.domain.motion import MotionState, MotionStatus, MoveCommand, MoveKind
from dvb_brain.domain.motion_plan import (
    Border,
    border_heading,
    calibrated_pose,
    moves_along,
    position_reached,
    reached,
)
from dvb_brain.domain.navmap import NavigationSettings
from dvb_brain.domain.planner import NoPath, Path, Planner
from dvb_brain.domain.robot import RobotGeometry
from dvb_brain.domain.strategy_model import Move
from dvb_brain.domain.world import WorldModel
from dvb_brain.ports.clock import Clock
from dvb_brain.ports.deadline import until
from dvb_brain.ports.motion import MotionPort

# New plans when the robot arrives out of the tolerance of the step: the board says ARRIVED within
# its own tolerances, so trying again and again would go round in circles (ADR 0014).
CORRECTIONS = 1


class NavResult(StrEnum):
    ARRIVED = auto()
    BLOCKED_BY_OPPONENT = auto()  # from TODO 6.3: still stopped by the avoidance
    NO_PATH = auto()
    TIMEOUT = auto()
    MOTION_FAULT = auto()  # a move ended BLOCKED or STOPPED, or arrived out of tolerance


class Navigator:
    def __init__(
        self,
        motion: MotionPort,
        clock: Clock,
        world: WorldModel,
        arena: Arena,
        side: Side,
        rules: MatchRules,
        geometry: RobotGeometry,
        settings: NavigationSettings,
    ) -> None:
        self._motion = motion
        self._clock = clock
        self._world = world
        self._arena = arena
        self._side = side
        self._rules = rules
        self._geometry = geometry
        self._settings = settings
        self._planner = Planner(arena, side, geometry, settings, world.snapshot(clock.now()))

    async def go_to(self, target: Move, deadline: float) -> NavResult:
        """Take the robot to target before deadline (s, on the Clock), then check its arrival.

        Each new plan, the correction included, goes from the measured pose to the absolute
        target. Cancelling go_to stops the robot (ADR 0010).
        """
        status = await self._still(deadline)
        if status is None:
            return NavResult.TIMEOUT
        pose = status.pose
        for _ in range(1 + CORRECTIONS):
            if reached(pose, target):
                return NavResult.ARRIVED
            moves = self._moves(pose, target)
            if moves is None:
                return NavResult.NO_PATH
            for cmd in moves:
                status = await self._move(cmd, deadline)
                if status is None:
                    return NavResult.TIMEOUT
                if status.state is not MotionState.ARRIVED:
                    return NavResult.MOTION_FAULT
                pose = status.pose
        return NavResult.ARRIVED if reached(pose, target) else NavResult.MOTION_FAULT

    async def push_until_blocked(self, distance: float, deadline: float) -> MotionStatus | None:
        """Push in a straight line, backwards when distance < 0, until both wheels block.

        Return the final status, BLOCKED on contact or ARRIVED after |distance| without one, or
        None at the deadline. Backwards, the lidar sees nothing: short and slow (ADR 0014).
        """
        if not (math.isfinite(distance) and distance != 0.0):
            raise ValueError(f"distance must be finite and not 0, got {distance}")
        if distance < -self._settings.reverse_max_distance:
            raise ValueError(
                f"distance must not back up over {self._settings.reverse_max_distance} m, "
                f"got {distance}"
            )
        # 0: the board limit, a push being bounded by its PUSH_VOLTAGE anyway (ADR 0010)
        max_speed = self._settings.reverse_max_speed if distance < 0.0 else 0.0
        cmd = MoveCommand(MoveKind.PUSH_UNTIL_BLOCKED, distance=distance, max_speed=max_speed)
        return await self._move(cmd, deadline)

    async def recalibrate(self, border: Border, max_distance: float, deadline: float) -> NavResult:
        """Push the rear against border, then set the pose it gives (architecture 7.2).

        ARRIVED once the pose is set; MOTION_FAULT without contact within max_distance, or when
        a move stops; TIMEOUT at the deadline.
        """
        if not (math.isfinite(max_distance) and max_distance > 0.0):
            # The push goes backwards: a max_distance <= 0 would push forwards, or not at all
            raise ValueError(f"max_distance must be finite and > 0, got {max_distance}")
        turn = MoveCommand(MoveKind.ROTATE_TO, theta=border_heading(border))
        turned = await self._move(turn, deadline)
        if turned is None:
            return NavResult.TIMEOUT
        if turned.state is not MotionState.ARRIVED:
            return NavResult.MOTION_FAULT
        pushed = await self.push_until_blocked(-max_distance, deadline)
        if pushed is None:
            return NavResult.TIMEOUT
        if pushed.state is not MotionState.BLOCKED:
            return NavResult.MOTION_FAULT
        still = await self._still(deadline)  # reset_pose needs a robot that does not move
        if still is None:
            return NavResult.TIMEOUT
        arena, rear = self._arena, self._geometry.rear
        pose = calibrated_pose(border, still.pose, arena.width, arena.depth, rear)
        if await until(self._clock, self._reset_pose(pose), deadline) is None:
            return NavResult.TIMEOUT
        return NavResult.ARRIVED

    def _moves(self, pose: Pose, target: Move) -> tuple[MoveCommand, ...] | None:
        """Return the moves from pose to target, or None when there is no path."""
        if position_reached(pose, target):
            path = Path((pose.position,))  # no GOTO on the spot: its direction is undefined
        else:
            world = self._world.snapshot(self._clock.now())
            self._planner = self._planner.updated(world)
            opponents = [track.value for track in world.opponents]
            forbidden = self._rules.forbidden_zones(self._side, world)
            planned = self._planner.plan(pose.position, target.position, opponents, forbidden)
            if isinstance(planned, NoPath):
                return None
            path = planned
        return moves_along(
            path, pose.theta, target.mode, target.theta, target.max_speed, self._settings
        )

    async def _move(self, cmd: MoveCommand, deadline: float) -> MotionStatus | None:
        """Run one move and return its final status, or None at the deadline.

        At the deadline the move is cancelled, which stops the robot (ADR 0010).
        """
        if self._clock.now() >= deadline:
            return None
        return await until(self._clock, self._motion.move(cmd), deadline)

    async def _still(self, deadline: float) -> MotionStatus | None:
        """Return a status of a robot that does not move, or None at the deadline.

        After a cancelled move, the robot still brakes: its pose is not yet the one to start from.
        """
        return await self._motion.status().wait_for(
            lambda status: status.state is not MotionState.MOVING, deadline - self._clock.now()
        )

    async def _reset_pose(self, pose: Pose) -> bool:
        await self._motion.reset_pose(pose)
        return True  # until gives None at the deadline only
