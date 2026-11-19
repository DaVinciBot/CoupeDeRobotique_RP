"""Bench test of the recalibration: push against a border, then reset the pose.

Table test tool, to be removed when the brain sends these messages itself
(TODO 15.1). It speaks to the motor Teensy with dvb_usb_com (messages of
docs/adr/0003-motion-protocol.md) and sends the heartbeat itself.

Usage, from the root of the repository:
    uv run --with pyserial python firmware/teensy_motor/bench/recalage.py COM5 bas \
        --params firmware/teensy_motor/bench/params.example.json
"""

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import serial

from dvb_usb_com.framing import FrameDecoder, encode_frame
from dvb_usb_com.messages import (
    ControlParam,
    Heartbeat,
    Message,
    MessageError,
    MotionState,
    MotionStatus,
    Move,
    MoveFlags,
    MoveKind,
    ResetPose,
    SetControlParams,
    StatusFlags,
    Stop,
    StopMode,
    decode_message,
)

BAUDRATE = 115200
HEARTBEAT_PERIOD = 0.05  # s, 20 Hz

# Example values, to be checked on the robot
D_BACK = 0.12  # wheel axis -> rear face, m, to be measured by the mechanics team
PUSH_SPEED = 0.05  # m/s
PUSH_DISTANCE = -0.4  # backwards, m
CLEARANCE = 0.08  # move away after the recalibration, m

# border: corrected axis, position of its inner face (m), heading of the robot
# with its back to the border (rad). Table: x from 0 to 3 m, y from 0 to 2 m
WALLS = {
    "bas": ("y", 0.0, math.pi / 2),
    "haut": ("y", 2.0, -math.pi / 2),
    "gauche": ("x", 0.0, 0.0),
    "droite": ("x", 3.0, math.pi),
}


@dataclass(frozen=True, slots=True)
class Pose:
    x: float  # m
    y: float  # m
    theta: float  # rad


def pose_against_wall(wall: str, pose: Pose) -> Pose:
    """Pose of the robot flat against the border, the other coordinate kept."""
    axis, position, theta = WALLS[wall]
    # the wheel axis is D_BACK away from the border, towards the table
    if axis == "y":
        return Pose(pose.x, position + D_BACK * math.sin(theta), theta)
    return Pose(position + D_BACK * math.cos(theta), pose.y, theta)


def same_pose(status: MotionStatus, pose: Pose) -> bool:
    angle = math.atan2(math.sin(status.theta - pose.theta), math.cos(status.theta - pose.theta))
    return abs(status.x - pose.x) < 0.005 and abs(status.y - pose.y) < 0.005 and abs(angle) < 0.01


@dataclass(slots=True)
class Teensy:
    """Link with the motor Teensy; poll() must be called often (heartbeat)."""

    link: serial.Serial
    decoder: FrameDecoder = field(default_factory=FrameDecoder)
    counter: int = 0
    next_heartbeat: float = 0.0
    status: MotionStatus | None = None

    def send(self, message: Message) -> None:
        self.link.write(encode_frame(message.pack()))

    def poll(self, duration: float) -> None:
        """Reads the Teensy and sends the heartbeat during duration (s)."""
        end = time.monotonic() + duration
        while True:
            now = time.monotonic()
            if now >= self.next_heartbeat:
                self.counter = (self.counter + 1) % 65536
                self.send(Heartbeat(self.counter))
                self.next_heartbeat = now + HEARTBEAT_PERIOD
            for data in self.decoder.feed(self.link.read(self.link.in_waiting or 1)):
                try:
                    message = decode_message(data)
                except MessageError as error:
                    print(f"Message ignoré : {error}")
                    continue
                if isinstance(message, MotionStatus):
                    self.status = message
            if now >= end:
                return

    def wait_status(self, timeout: float) -> MotionStatus | None:
        """Next status received before timeout (s)."""
        self.status = None
        end = time.monotonic() + timeout
        while self.status is None and time.monotonic() < end:
            self.poll(0.01)
        return self.status

    def move(self, move: Move, timeout: float) -> MotionStatus | None:
        """Sends a move and waits for its end; None if it never ends."""
        self.send(move)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            status = self.wait_status(0.5)
            # the move_id says that the status comes after the command
            if (
                status is not None
                and status.move_id == move.move_id
                and status.state != MotionState.MOVING
            ):
                return status
        return None


def configure(teensy: Teensy, params: dict[str, float]) -> bool:
    """Sends every setting; the Teensy stays inert until it has them all."""
    for param in ControlParam:
        teensy.send(SetControlParams(param, params[param.name.lower()]))
        teensy.poll(0.005)
    status = teensy.wait_status(1.0)
    return status is not None and bool(status.flags & StatusFlags.CONFIGURED)


def apply_pose(teensy: Teensy, target: Pose, attempts: int = 3) -> MotionStatus | None:
    """Sends RESET_POSE until the new pose is seen in the status."""
    # the Teensy does not answer the reset, and ignores it while moving
    for _ in range(attempts):
        teensy.send(ResetPose(target.x, target.y, target.theta))
        for _ in range(5):
            status = teensy.wait_status(0.2)
            if status is not None and same_pose(status, target):
                return status
    return None


def recalibrate(teensy: Teensy, wall: str) -> bool:
    print(f"Poussée vers la bordure {wall}...")
    push = Move(
        1, MoveKind.PUSH_UNTIL_BLOCKED, MoveFlags.NONE, 0, 0, 0, PUSH_DISTANCE, PUSH_SPEED, 0
    )
    status = teensy.move(push, timeout=20.0)
    if status is None:
        print("La poussée ne s'est pas terminée")
        return False
    if status.state != MotionState.BLOCKED:
        print(f"Aucune bordure touchée après {abs(PUSH_DISTANCE)} m ({status.state.name})")
        return False
    pose = Pose(status.x, status.y, status.theta)
    print(f"Bloqué, pose odométrique : {pose}")

    target = pose_against_wall(wall, pose)
    status = apply_pose(teensy, target)
    if status is None:
        print("La Teensy n'a pas appliqué la nouvelle pose")
        return False
    print(f"Pose recalée : {target}")

    clearance = Move(
        2,
        MoveKind.STRAIGHT,
        MoveFlags.NONE,
        0,
        0,
        0,
        CLEARANCE,
        0,
        0,
    )
    print("Dégagement...")
    status = teensy.move(clearance, timeout=10.0)
    if status is None or status.state != MotionState.ARRIVED:
        print("Le dégagement ne s'est pas terminé")
        return False
    print(f"Terminé, pose : x = {status.x:.3f} m, y = {status.y:.3f} m, theta = {status.theta:.3f}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("port", help="port série de la Teensy moteur, ex. COM5")
    parser.add_argument("wall", choices=WALLS, help="bordure derrière le robot")
    parser.add_argument("--params", type=Path, required=True, help="réglages (JSON)")
    args = parser.parse_args()

    params = json.loads(args.params.read_text(encoding="utf-8"))
    teensy = Teensy(serial.Serial(args.port, BAUDRATE, timeout=0.01))
    try:
        if not configure(teensy, params):
            print("La Teensy n'a pas accepté les réglages")
            return 1
        return 0 if recalibrate(teensy, args.wall) else 1
    finally:
        teensy.send(Stop(StopMode.URGENT))


if __name__ == "__main__":
    sys.exit(main())
