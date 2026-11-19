"""Remote vision of the tests: the test sets the observations and reads the events sent."""

from dvb_brain.domain.remote_vision import RemoteEvent, RemoteObservations
from dvb_brain.ports.clock import Clock
from dvb_brain.ports.watch import Watch


class FakeRemoteVision:
    def __init__(self, clock: Clock) -> None:
        self._observations = Watch[RemoteObservations](clock)
        self.sent: list[RemoteEvent] = []

    def observations(self) -> Watch[RemoteObservations]:
        return self._observations

    async def send(self, event: RemoteEvent) -> None:
        self.sent.append(event)
