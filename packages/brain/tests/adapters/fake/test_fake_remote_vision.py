import pytest

from dvb_brain.adapters.fake.clock import FakeClock
from dvb_brain.adapters.fake.remote_vision import FakeRemoteVision
from dvb_brain.domain.arena import Side
from dvb_brain.domain.remote_vision import MatchStarted, SideChosen
from dvb_brain.ports.remote_vision import RemoteVisionPort

pytestmark = pytest.mark.asyncio


async def test_keeps_the_events_sent() -> None:
    fake = FakeRemoteVision(FakeClock())
    remote: RemoteVisionPort = fake

    await remote.send(SideChosen(Side.BLUE))
    await remote.send(MatchStarted(t0=3.0))

    assert fake.sent == [SideChosen(Side.BLUE), MatchStarted(t0=3.0)]
    assert remote.observations().get() is None
