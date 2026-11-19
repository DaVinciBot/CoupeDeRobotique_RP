"""Hardware and clock interfaces (typing.Protocol) used by the services, and their bundle."""

from dataclasses import dataclass

from dvb_brain.ports.actuators import ActuatorPort
from dvb_brain.ports.clock import Clock
from dvb_brain.ports.lidar import LidarPort
from dvb_brain.ports.motion import MotionPort
from dvb_brain.ports.remote_vision import RemoteVisionPort
from dvb_brain.ports.start_switch import StartSwitchPort
from dvb_brain.ports.telemetry import TelemetryPort


@dataclass(frozen=True, slots=True)
class Ports:
    """Every port of the brain; only app knows which adapters are behind (ADR 0011).

    No port for the emergency stop button: the motor board reports it in
    MotionStatus.emergency_stop.
    """

    clock: Clock
    motion: MotionPort
    actuators: ActuatorPort
    lidar: LidarPort
    remote_vision: RemoteVisionPort
    start_switch: StartSwitchPort
    telemetry: TelemetryPort
