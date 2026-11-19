"""Motor board of the tests: ideal moves in trapezoids, and the failures a test injects.

run() publishes a status every status_period, like the board does (ADR 0011); move() returns
on the status that ends its move_id, as the Teensy adapter will (TODO 15.1). The profiles stay
private here until the planner (TODO 5.2) or the simulated base (TODO 11.2) needs them.
"""

import asyncio
import math
from dataclasses import dataclass

from dvb_brain.domain.geometry import Pose, normalize_angle, shortest_rotation
from dvb_brain.domain.motion import (
    GoToPoint,
    MotionState,
    MotionStatus,
    MoveCommand,
    PushUntilBlocked,
    RotateBy,
    RotateTo,
    StopMode,
    Straight,
)
from dvb_brain.ports.clock import Clock
from dvb_brain.ports.watch import Watch


@dataclass(frozen=True, slots=True)
class _Profile:
    """Phases of constant acceleration (duration, acceleration) from the speed v0, >= 0.

    Lengths and speeds are in m and m/s for a translation, rad and rad/s for a rotation.
    """

    v0: float
    phases: tuple[tuple[float, float], ...]
    length: float  # covered once over

    @property
    def duration(self) -> float:
        return sum(duration for duration, _ in self.phases)

    def at(self, t: float) -> tuple[float, float]:
        """Return the length covered and the speed t seconds after the start."""
        if t >= self.duration:
            return self.length, 0.0  # exactly at the end, whatever the rounding
        covered, speed = 0.0, self.v0
        for duration, accel in self.phases:
            dt = min(t, duration)
            covered += speed * dt + accel * dt * dt / 2
            speed += accel * dt
            t -= dt
        return covered, speed


def _trapezoid(length: float, max_speed: float, max_accel: float) -> _Profile:
    """From rest to rest over length >= 0; a triangle when too short to reach max_speed."""
    ramps = max_speed**2 / max_accel  # length of the speed-up and the slow-down together
    if length <= ramps:
        ramp = math.sqrt(length * max_accel) / max_accel
        return _Profile(0.0, ((ramp, max_accel), (ramp, -max_accel)), length)
    ramp = max_speed / max_accel
    cruise = (length - ramps) / max_speed
    return _Profile(0.0, ((ramp, max_accel), (cruise, 0.0), (ramp, -max_accel)), length)


def _braking(speed: float, decel: float) -> _Profile:
    return _Profile(speed, ((speed / decel, -decel),), speed**2 / (2 * decel))


@dataclass(frozen=True, slots=True)
class _Kinematics:
    pose: Pose
    v: float  # m/s
    omega: float  # rad/s
    state: MotionState


@dataclass(frozen=True, slots=True)
class _Segment:
    """A straight line or a rotation on the spot."""

    start: Pose
    start_time: float
    profile: _Profile
    direction: float  # +1 forwards or counter-clockwise, -1 the other way
    rotation: bool
    block_after: float | None = None  # m: the robot hits something there (translation)

    @property
    def end_time(self) -> float:
        return self.start_time + self.profile.duration

    def at(self, now: float) -> tuple[Pose, float]:
        """Return the pose and the signed speed at now."""
        covered, speed = self.profile.at(now - self.start_time)
        return self._pose(covered), self.direction * speed

    def blocked_pose(self, now: float) -> Pose | None:
        if self.block_after is None or self.profile.at(now - self.start_time)[0] < self.block_after:
            return None
        return self._pose(self.block_after)

    def _pose(self, covered: float) -> Pose:
        signed = self.direction * covered
        if self.rotation:
            return Pose(self.start.x, self.start.y, normalize_angle(self.start.theta + signed))
        position = self.start.position + self.start.heading_vector * signed
        return Pose(position.x, position.y, self.start.theta)


@dataclass(frozen=True, slots=True)
class _Run:
    """The segments of the move the board executes, one after the other."""

    start: Pose
    segments: tuple[_Segment, ...]
    end_state: MotionState

    def at(self, now: float) -> _Kinematics:
        pose = self.start
        for segment in self.segments:
            blocked = segment.blocked_pose(now)
            if blocked is not None:
                return _Kinematics(blocked, 0.0, 0.0, MotionState.BLOCKED)
            if now < segment.end_time:
                pose, speed = segment.at(now)
                if segment.rotation:
                    return _Kinematics(pose, 0.0, speed, MotionState.MOVING)
                return _Kinematics(pose, speed, 0.0, MotionState.MOVING)
            pose, _ = segment.at(segment.end_time)
        return _Kinematics(pose, 0.0, 0.0, self.end_state)


class FakeMotion:
    def __init__(
        self,
        clock: Clock,
        *,
        pose: Pose,
        rotation_speed: float,  # rad/s
        rotation_accel: float,  # rad/s²
        stop_decel: float,  # m/s², of stop(SMOOTH)
        status_period: float,  # s
    ) -> None:
        self._clock = clock
        self._rotation_speed = rotation_speed
        self._rotation_accel = rotation_accel
        self._stop_decel = stop_decel
        self._status_period = status_period
        self._status = Watch[MotionStatus](clock)
        # The board
        self._boot_id = 1
        self._boot_time = clock.now()
        self._board_move_id = 0
        self._rest = _Kinematics(pose, 0.0, 0.0, MotionState.STOPPED)
        self._run: _Run | None = None
        # The port
        self._last_move_id = 0
        self._move: tuple[int, asyncio.Future[MotionStatus]] | None = None
        self._reset: tuple[Pose, asyncio.Future[None]] | None = None
        self._urgent = False
        # Failures injected by the test
        self._silent = False
        self._emergency_stop = False
        self._block_after: float | None = None
        # What the board received
        self.heartbeats: list[float] = []
        self.stops: list[tuple[float, StopMode]] = []

    # Motion port

    async def move(self, cmd: MoveCommand) -> MotionStatus:
        if self._urgent:
            raise RuntimeError("urgent stop: no move until the brain restarts")
        if self._move is not None:
            raise RuntimeError(f"move {self._move[0]} still runs: one move at a time")
        self._last_move_id += 1
        done: asyncio.Future[MotionStatus] = asyncio.get_running_loop().create_future()
        self._move = (self._last_move_id, done)
        if not self._silent:
            self._start(self._last_move_id, cmd)
        try:
            return await done
        except asyncio.CancelledError:
            if not self._urgent:
                self._send_stop(StopMode.SMOOTH)
            raise
        finally:
            self._move = None

    async def stop(self, mode: StopMode) -> None:
        if mode is StopMode.URGENT:
            self._urgent = True
        elif self._urgent:
            return  # nothing softens an urgent stop (ADR 0010)
        self._send_stop(mode)

    async def heartbeat(self) -> None:
        self.heartbeats.append(self._clock.now())

    async def reset_pose(self, pose: Pose) -> None:
        if self._urgent:
            raise RuntimeError("urgent stop: no reset until the brain restarts")
        last = self._status.get()
        if self._move is not None or (last is not None and last.state is MotionState.MOVING):
            raise RuntimeError("the robot moves: reset the pose once it is still")
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._reset = (pose, done)
        if not self._silent:
            self._rest = _Kinematics(pose, 0.0, 0.0, self._rest.state)
        try:
            await done
        finally:
            self._reset = None

    def status(self) -> Watch[MotionStatus]:
        return self._status

    def link_ok(self) -> bool:
        return True  # a silent board keeps its port open

    # The board

    async def run(self) -> None:
        """Publish a status every status_period until cancelled."""
        while True:
            self._publish()
            await self._clock.sleep(self._status_period)

    # Failures injected by the test

    def block_after(self, distance: float) -> None:
        """Make the next translation end BLOCKED after distance m."""
        self._block_after = distance

    def silence(self) -> None:
        """The board stops answering: no status any more, every command is lost."""
        self._silent = True

    def restart(self) -> None:
        """The board restarts: new boot_id, pose and move lost."""
        self._silent = False
        self._boot_id += 1
        self._boot_time = self._clock.now()
        self._board_move_id = 0
        self._run = None
        self._rest = _Kinematics(Pose(0.0, 0.0, 0.0), 0.0, 0.0, MotionState.STOPPED)

    def press_emergency_stop(self) -> None:
        """The drivers lose their power: the robot stops at once, and moves no more."""
        self._emergency_stop = True
        self._halt()

    def release_emergency_stop(self) -> None:
        self._emergency_stop = False

    # Inside the board

    def _update(self) -> _Kinematics:
        if self._run is None:
            return self._rest
        kinematics = self._run.at(self._clock.now())
        if kinematics.state is not MotionState.MOVING:
            self._rest, self._run = kinematics, None
        return kinematics

    def _publish(self) -> None:
        kinematics = self._update()
        if self._silent:
            return
        status = MotionStatus(
            move_id=self._board_move_id,
            state=kinematics.state,
            pose=kinematics.pose,
            v=kinematics.v,
            omega=kinematics.omega,
            emergency_stop=self._emergency_stop,
            teensy_time=self._clock.now() - self._boot_time,
            boot_id=self._boot_id,
        )
        self._status.set(status)
        # A future may already be done, cancelled with its task that has not run yet.
        if self._move is not None:
            move_id, moved = self._move
            ended = move_id == status.move_id and status.state is not MotionState.MOVING
            if ended and not moved.done():
                moved.set_result(status)
        if self._reset is not None:
            pose, reset = self._reset
            if pose == status.pose and not reset.done():
                reset.set_result(None)

    def _start(self, move_id: int, cmd: MoveCommand) -> None:
        now, pose = self._clock.now(), self._update().pose
        self._board_move_id = move_id
        if self._emergency_stop:  # no power: the move ends where it starts
            self._run = _Run(pose, (), MotionState.STOPPED)
            return
        match cmd:
            case RotateBy(angle=angle):
                segments = (self._rotation(pose, now, angle),)
            case RotateTo(heading=heading):
                segments = (self._rotation(pose, now, shortest_rotation(pose.theta, heading)),)
            case Straight(distance=distance, max_speed=speed, max_accel=accel):
                segments = (self._translation(pose, now, distance, speed, accel),)
            case GoToPoint(target=target, max_speed=speed, max_accel=accel):
                offset = target - pose.position
                turn = shortest_rotation(pose.theta, offset.angle())
                rotation = self._rotation(pose, now, turn)
                facing = Pose(pose.x, pose.y, normalize_angle(pose.theta + turn))
                line = self._translation(facing, rotation.end_time, offset.norm(), speed, accel)
                segments = (rotation, line)
            case PushUntilBlocked(max_distance=distance, max_speed=speed, max_accel=accel):
                segments = (self._translation(pose, now, distance, speed, accel),)
        end = MotionState.STOPPED if isinstance(cmd, PushUntilBlocked) else MotionState.ARRIVED
        self._run = _Run(pose, segments, end)

    def _rotation(self, pose: Pose, start: float, angle: float) -> _Segment:
        profile = _trapezoid(abs(angle), self._rotation_speed, self._rotation_accel)
        return _Segment(pose, start, profile, math.copysign(1.0, angle), rotation=True)

    def _translation(
        self, pose: Pose, start: float, distance: float, speed: float, accel: float
    ) -> _Segment:
        block, self._block_after = self._block_after, None
        profile = _trapezoid(abs(distance), speed, accel)
        direction = math.copysign(1.0, distance)
        return _Segment(pose, start, profile, direction, rotation=False, block_after=block)

    def _send_stop(self, mode: StopMode) -> None:
        self.stops.append((self._clock.now(), mode))
        if self._silent:
            return
        if mode is StopMode.URGENT:
            self._halt()
        else:
            self._brake()

    def _halt(self) -> None:
        kinematics = self._update()
        if self._run is not None:
            self._rest = _Kinematics(kinematics.pose, 0.0, 0.0, MotionState.STOPPED)
            self._run = None

    def _brake(self) -> None:
        kinematics = self._update()
        if self._run is None:
            return
        rotation = kinematics.omega != 0.0
        speed = kinematics.omega if rotation else kinematics.v
        if speed == 0.0:  # between two segments of a move
            self._halt()
            return
        decel = self._rotation_accel if rotation else self._stop_decel
        segment = _Segment(
            kinematics.pose,
            self._clock.now(),
            _braking(abs(speed), decel),
            math.copysign(1.0, speed),
            rotation=rotation,
        )
        self._run = _Run(kinematics.pose, (segment,), MotionState.STOPPED)
