"""Banc de test du recalage : pousse contre une bordure puis recale la pose.

Outil de test sur table, à supprimer quand le brain enverra lui-même ces
messages (TODO 15.1). Il parle à la Teensy moteur avec le protocole usb_com
actuel (signature de 4 octets, CRC-8) et les messages de messages.h.

Usage, depuis la racine du dépôt :
    uv run --no-project --with pyserial python firmware/teensy_motor/bench/recalage.py COM5 bas
"""

import argparse
import math
import struct
import sys
import time
from dataclasses import dataclass

import serial

BAUDRATE = 115200
SIGNATURE = bytes([0xBA, 0xDD, 0x1C, 0xC5])

# ID des messages, comme dans messages.h
SET_TARGET_POSITION = 0
RESET_POSE = 2
PUSH_UNTIL_BLOCKED = 11
UPDATE_ROLLING_BASIS = 128

# statut de la base roulante, comme Rolling_Basis::Status
STOPPED = 0
MOVING = 1
BLOCKED = 2

# Valeurs d'exemple, à valider sur le robot
D_BACK_CM = 12.0  # centre des roues -> face arrière, à mesurer par la méca
PUSH_SPEED_CM_S = -5.0  # recul
PUSH_MAX_DISTANCE_CM = 40.0
CLEARANCE_CM = 8.0  # dégagement après le recalage

# bordure : axe recalé, position de sa face intérieure (cm), cap du robot dos à
# la bordure (rad). Repère de la table : x de 0 à 300 cm, y de 0 à 200 cm
WALLS = {
    "bas": ("y", 0.0, math.pi / 2),
    "haut": ("y", 200.0, -math.pi / 2),
    "gauche": ("x", 0.0, 0.0),
    "droite": ("x", 300.0, math.pi),
}


@dataclass(frozen=True, slots=True)
class Pose:
    x: float  # en cm
    y: float  # en cm
    theta: float  # en rad


@dataclass(frozen=True, slots=True)
class Status:
    pose: Pose
    state: int


def crc8(data: bytes) -> int:
    """CRC-8 de polynôme 0x07, le même que crc.cpp."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def encode(payload: bytes) -> bytes:
    """Trame usb_com : [message][taille][crc][signature]."""
    body = payload + bytes([len(payload)])
    return body + bytes([crc8(body)]) + SIGNATURE


def decode(frame: bytes) -> bytes | None:
    """Message contenu dans une trame sans sa signature, None si elle est abîmée."""
    if len(frame) < 3:
        return None
    size = frame[-2]
    if size == 0 or len(frame) < size + 2:
        return None
    body = frame[-2 - size : -1]
    if crc8(body) != frame[-1]:
        return None
    return body[:-1]


def pose_against_wall(wall: str, pose: Pose) -> Pose:
    """Pose du robot plaqué dos à la bordure, l'autre coordonnée est gardée."""
    axis, position, theta = WALLS[wall]
    # le centre des roues est à D_BACK_CM de la bordure, vers la table
    if axis == "y":
        return Pose(pose.x, position + D_BACK_CM * math.sin(theta), theta)
    return Pose(position + D_BACK_CM * math.cos(theta), pose.y, theta)


def same_pose(a: Pose, b: Pose) -> bool:
    angle = math.atan2(math.sin(a.theta - b.theta), math.cos(a.theta - b.theta))
    return abs(a.x - b.x) < 0.5 and abs(a.y - b.y) < 0.5 and abs(angle) < 0.01


class Teensy:
    """Envoi des messages et lecture du statut de la Teensy moteur."""

    def __init__(self, port: str) -> None:
        self.serial = serial.Serial(port, BAUDRATE, timeout=0.05)
        self.buffer = bytearray()

    def send(self, payload: bytes) -> None:
        self.serial.write(encode(payload))

    def push_until_blocked(self, speed: float, max_distance: float) -> None:
        self.send(struct.pack("<Bdd", PUSH_UNTIL_BLOCKED, speed, max_distance))

    def reset_pose(self, pose: Pose) -> None:
        self.send(struct.pack("<Bddd", RESET_POSE, pose.x, pose.y, pose.theta))

    def set_target(self, pose: Pose) -> None:
        self.send(struct.pack("<Bddd", SET_TARGET_POSITION, pose.x, pose.y, pose.theta))

    def read_status(self, timeout: float) -> Status | None:
        """Prochain statut reçu, None si rien n'arrive avant timeout (s)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.buffer += self.serial.read(self.serial.in_waiting or 1)
            while (index := self.buffer.find(SIGNATURE)) >= 0:
                message = decode(bytes(self.buffer[:index]))
                del self.buffer[: index + len(SIGNATURE)]
                if message is not None and message[0] == UPDATE_ROLLING_BASIS:
                    _, x, y, theta, state = struct.unpack("<BdddB", message)
                    return Status(Pose(x, y, theta), state)
        return None

    def wait_end_of_move(self, timeout: float) -> Status | None:
        """Attend que le mouvement démarre puis s'arrête, et renvoie le statut final."""
        started = False
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            status = self.read_status(end - time.monotonic())
            if status is None:
                return None
            # les statuts envoyés avant la commande disent encore STOPPED
            if status.state == MOVING:
                started = True
            elif started:
                return status
        return None


def apply_pose(teensy: Teensy, target: Pose, attempts: int = 3) -> Status | None:
    """Envoie RESET_POSE jusqu'à voir la nouvelle pose dans le statut."""
    # la Teensy ne répond pas au reset, et l'ignore si le robot bouge
    for _ in range(attempts):
        teensy.reset_pose(target)
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            status = teensy.read_status(end - time.monotonic())
            if status is not None and same_pose(status.pose, target):
                return status
    return None


def recalage(teensy: Teensy, wall: str) -> bool:
    print(f"Poussée vers la bordure {wall}...")
    teensy.push_until_blocked(PUSH_SPEED_CM_S, PUSH_MAX_DISTANCE_CM)
    status = teensy.wait_end_of_move(timeout=20.0)
    if status is None:
        print("Pas de statut de la Teensy")
        return False
    if status.state != BLOCKED:
        print(f"Aucune bordure touchée après {PUSH_MAX_DISTANCE_CM} cm")
        return False
    print(f"Bloqué, pose odométrique : {status.pose}")

    target = pose_against_wall(wall, status.pose)
    status = apply_pose(teensy, target)
    if status is None:
        print("La Teensy n'a pas appliqué la nouvelle pose")
        return False
    print(f"Pose recalée : {status.pose}")

    clearance = Pose(
        target.x + CLEARANCE_CM * math.cos(target.theta),
        target.y + CLEARANCE_CM * math.sin(target.theta),
        target.theta,
    )
    print("Dégagement...")
    teensy.set_target(clearance)
    status = teensy.wait_end_of_move(timeout=10.0)
    if status is None or status.state != STOPPED:
        print("Le dégagement ne s'est pas terminé")
        return False
    print(f"Terminé, pose : {status.pose}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("port", help="port série de la Teensy moteur, ex. COM5")
    parser.add_argument("wall", choices=WALLS, help="bordure derrière le robot")
    args = parser.parse_args()

    teensy = Teensy(args.port)
    return 0 if recalage(teensy, args.wall) else 1


if __name__ == "__main__":
    sys.exit(main())
