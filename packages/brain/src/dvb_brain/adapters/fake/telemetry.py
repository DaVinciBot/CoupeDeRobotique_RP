"""Telemetry of the tests: keeps every message published."""


class FakeTelemetry:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    def publish(self, topic: str, msg: object) -> None:
        self.published.append((topic, msg))
