from dvb_brain.adapters.fake.telemetry import FakeTelemetry
from dvb_brain.ports.telemetry import TelemetryPort


def test_keeps_the_messages_published() -> None:
    fake = FakeTelemetry()
    telemetry: TelemetryPort = fake

    telemetry.publish("match.state", "running")

    assert fake.published == [("match.state", "running")]
