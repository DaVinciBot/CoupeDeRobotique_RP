"""Motor board of the tests: ideal moves in trapezoids, and the failures a test injects.

It behaves as the motor board contract says (ADR 0003), with ideal profiles. run() publishes a
status every status_period, like the board does (ADR 0011); move() returns on the status that
ends its move_id, as the Teensy adapter will (TODO 15.1). The profiles stay private here until
the planner (TODO 5.2) or the simulated base (TODO 11.2) needs them.
"""

import asyncio
import math
from dataclasses import dataclass, replace

from dvb_brain.domain.geometry import Pose, Vec2, normalize_angle, shortest_rotation
from dvb_brain.domain.motion import MotionState, MotionStatus, MoveCommand, MoveKind, StopMode
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


def _trapezoid(length: float, max_speed: float, max_accel: float, v0: float = 0.0) -> _Profile:
    """From the speed v0 to rest over length >= 0, at max_speed when there is room for it.

    v0 goes up or down to the peak speed, which stays there, then brakes to stop on length; a
    triangle when too short to reach max_speed. v0 must leave room to brake within length.
    """
    peak = min(max_speed, math.sqrt(max_accel * length + v0 * v0 / 2))
    change = abs(peak - v0) / max_accel
    change_length = (v0 + peak) / 2 * change
    brake_length = peak * peak / (2 * max_accel)
    cruise = max(length - change_length - brake_length, 0.0) / peak if peak > 0.0 else 0.0
    accel = max_accel if peak >= v0 else -max_accel
    return _Profile(v0, ((change, accel), (cruise, 0.0), (peak / max_accel, -max_accel)), length)


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
    line: int | None = None  # index of the straight line of a GOTO
    push: bool = False

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


def _valid(cmd: MoveCommand) -> bool:
    """What the board accepts (ADR 0003): finite values, and a push that goes somewhere."""
    values = (cmd.x, cmd.y, cmd.theta, cmd.distance, cmd.max_speed, cmd.max_accel)
    no_push = cmd.kind is not MoveKind.PUSH_UNTIL_BLOCKED or cmd.distance != 0.0
    return all(math.isfinite(value) for value in values) and no_push


class FakeMotion:
    def __init__(
        self,
        clock: Clock,
        *,
        pose: Pose,
        max_speed: float,  # m/s, board settings received at start-up (ADR 0003)
        max_accel: float,  # m/s², also the deceleration of stop(SMOOTH)
        max_angular_speed: float,  # rad/s
        max_angular_accel: float,  # rad/s²
        vbat: float,  # V, the battery voltage the board reports
        status_period: float,  # s
    ) -> None:
        self._clock = clock
        self._max_speed = max_speed
        self._max_accel = max_accel
        self._max_angular_speed = max_angular_speed
        self._max_angular_accel = max_angular_accel
        self._vbat = vbat
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
        self._goto: tuple[int, MoveCommand] | None = None  # the running GOTO, until a stop
        self._reset: tuple[Pose, asyncio.Future[None]] | None = None
        self._urgent = False
        # Failures injected by the test
        self._silent = False
        self._emergency_stop = False
        self._block_after: float | None = None
        self._misses = 0
        self._miss = Pose(0.0, 0.0, 0.0)
        # What the board received
        self.heartbeats: list[float] = []
        self.stops: list[tuple[float, StopMode]] = []
        self.moves: list[MoveCommand] = []  # one per move(); a set_max_speed resend not counted

    # Motion port

    async def move(self, cmd: MoveCommand) -> MotionStatus:
        if self._urgent:
            raise RuntimeError("urgent stop: no move until the brain restarts")
        if self._move is not None:
            raise RuntimeError(f"move {self._move[0]} still runs: one move at a time")
        self._last_move_id += 1
        done: asyncio.Future[MotionStatus] = asyncio.get_running_loop().create_future()
        self._move = (self._last_move_id, done)
        self._goto = (self._last_move_id, cmd) if cmd.kind is MoveKind.GOTO else None
        self.moves.append(cmd)
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
            self._goto = None

    async def stop(self, mode: StopMode) -> None:
        self._goto = None
        if mode is StopMode.URGENT:
            self._urgent = True
        elif self._urgent:
            return  # nothing softens an urgent stop (ADR 0010)
        self._send_stop(mode)

    async def set_max_speed(self, max_speed: float) -> bool:
        if not (math.isfinite(max_speed) and max_speed > 0.0):
            raise ValueError(f"max_speed must be finite and > 0, got {max_speed}")
        if self._urgent or self._goto is None:
            return False
        move_id, goto = self._goto
        self._goto = (move_id, replace(goto, max_speed=max_speed))
        if not self._silent:
            self._change_speed(self._goto[1])
        return True

    async def heartbeat(self) -> None:
        self.heartbeats.append(self._clock.now())

    async def reset_pose(self, pose: Pose) -> None:
        if self._urgent:
            raise RuntimeError("urgent stop: no reset until the brain restarts")
        last = self._status.get()
        moving = last is not None and last.state is MotionState.MOVING
        self._update()
        # Still braking after a cancelled move, maybe before any status has shown it
        if self._move is not None or moving or self._run is not None:
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

    def miss_next_gotos(self, count: int, offset: Vec2, angle: float = 0.0) -> None:
        """Make the next count GOTOs end off their target by offset, and off their heading.

        The odometry sees the miss, as after a slip of the wheels: the status shows it.
        """
        self._misses = count
        self._miss = Pose(offset.x, offset.y, angle)

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
        """The drivers lose their power: the robot stops at once, and the board ignores MOVE."""
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
            vbat=self._vbat,
            teensy_time=self._clock.now() - self._boot_time,
            boot_id=self._boot_id,
            heartbeat=len(self.heartbeats),
            configured=True,
            emergency_stop=self._emergency_stop,
            heartbeat_lost=False,  # no watchdog here: the virtual Teensy has it (ADR 0011)
            vbat_missing=False,
            estop_sensor_missing=False,
            trace_running=False,
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

    def _limits(self, cmd: MoveCommand) -> tuple[float, float]:
        """Speed and acceleration of a translation, brought back to the board settings."""
        speed = min(cmd.max_speed, self._max_speed) if cmd.max_speed > 0.0 else self._max_speed
        accel = min(cmd.max_accel, self._max_accel) if cmd.max_accel > 0.0 else self._max_accel
        return speed, accel

    def _start(self, move_id: int, cmd: MoveCommand) -> None:
        if self._emergency_stop or not _valid(cmd):  # ignored: move_id does not change
            return
        now, pose = self._clock.now(), self._update().pose
        # Still braking after a cancelled move: the new one starts once the robot is still.
        braking = self._run.segments if self._run is not None else ()
        if braking:
            now = braking[-1].end_time
            pose, _ = braking[-1].at(now)
        self._board_move_id = move_id
        speed, accel = self._limits(cmd)
        line: int | None = None
        match cmd.kind:
            case MoveKind.ROTATE_BY:
                segments = (self._rotation(pose, now, cmd.theta),)
            case MoveKind.ROTATE_TO:
                segments = (self._rotation(pose, now, shortest_rotation(pose.theta, cmd.theta)),)
            case MoveKind.STRAIGHT | MoveKind.PUSH_UNTIL_BLOCKED:
                segments = (self._translation(pose, now, cmd.distance, speed, accel),)
            case MoveKind.GOTO:
                if self._misses > 0:
                    self._misses -= 1
                    miss = self._miss
                    cmd = replace(
                        cmd, x=cmd.x + miss.x, y=cmd.y + miss.y, theta=cmd.theta + miss.theta
                    )
                segments = self._goto_segments(pose, now, cmd, speed, accel)
                line = len(braking) + 1
        push = cmd.kind is MoveKind.PUSH_UNTIL_BLOCKED
        self._run = _Run(pose, braking + segments, MotionState.ARRIVED, line, push)

    def _goto_segments(
        self, pose: Pose, now: float, cmd: MoveCommand, speed: float, accel: float
    ) -> tuple[_Segment, ...]:
        """Turn to face the target (or show it the rear), straight line, then the heading."""
        offset = Vec2(cmd.x, cmd.y) - pose.position
        heading = offset.angle() if offset.norm() > 0.0 else pose.theta
        if cmd.reverse and offset.norm() > 0.0:
            heading += math.pi
        turn = self._rotation(pose, now, shortest_rotation(pose.theta, heading))
        facing, _ = turn.at(turn.end_time)
        distance = -offset.norm() if cmd.reverse else offset.norm()
        line = self._translation(facing, turn.end_time, distance, speed, accel)
        if not cmd.has_heading:
            return turn, line
        there, _ = line.at(line.end_time)
        final = self._rotation(there, line.end_time, shortest_rotation(there.theta, cmd.theta))
        return turn, line, final

    def _change_speed(self, cmd: MoveCommand) -> None:
        """The running GOTO comes again with another max_speed: it goes on (ADR 0003)."""
        kinematics = self._update()
        run, now = self._run, self._clock.now()
        if self._emergency_stop or run is None or run.line is None:
            return  # ignored, or already over: a GOTO there again would not move
        line = run.segments[run.line]
        if now >= line.end_time:
            return  # in the final turn: no translation left to slow down
        speed, accel = self._limits(cmd)
        if now <= line.start_time:  # still turning to face the target
            start, start_time, v0, covered = line.start, line.start_time, 0.0, 0.0
        else:
            start, start_time, v0 = kinematics.pose, now, abs(kinematics.v)
            covered = line.profile.at(now - line.start_time)[0]
        block = None if line.block_after is None else line.block_after - covered
        profile = _trapezoid(line.profile.length - covered, speed, accel, v0)
        new_line = replace(
            line, start=start, start_time=start_time, profile=profile, block_after=block
        )
        there, _ = new_line.at(new_line.end_time)
        after = tuple(
            replace(segment, start=there, start_time=new_line.end_time)
            for segment in run.segments[run.line + 1 :]
        )
        self._run = replace(run, segments=(*run.segments[: run.line], new_line, *after))

    def _rotation(self, pose: Pose, start: float, angle: float) -> _Segment:
        profile = _trapezoid(abs(angle), self._max_angular_speed, self._max_angular_accel)
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
        # A push is the last segment; before it starts, the robot brakes from the previous move.
        pushing = self._run.push and self._clock.now() >= self._run.segments[-1].start_time
        if speed == 0.0 or pushing:  # between two segments, or a push: cut the motors
            self._halt()
            return
        decel = self._max_angular_accel if rotation else self._max_accel
        segment = _Segment(
            kinematics.pose,
            self._clock.now(),
            _braking(abs(speed), decel),
            math.copysign(1.0, speed),
            rotation=rotation,
        )
        self._run = _Run(kinematics.pose, (segment,), MotionState.STOPPED)
