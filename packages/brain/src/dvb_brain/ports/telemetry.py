"""Telemetry port: what the brain shows on the dashboard and keeps in the logs."""

from typing import Protocol


class TelemetryPort(Protocol):
    def publish(self, topic: str, msg: object) -> None:
        """Publish without waiting; dropped when nobody listens. Never raises."""
        ...
