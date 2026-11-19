"""Start cord of the tests: the test inserts and pulls it."""

import asyncio

from dvb_brain.ports.clock import Clock


class FakeStartSwitch:
    def __init__(self, clock: Clock, *, inserted: bool) -> None:
        self._clock = clock
        self._inserted = inserted
        self._waiters: list[asyncio.Future[float]] = []

    def inserted(self) -> bool:
        return self._inserted

    async def wait_pulled(self) -> float:
        waiter: asyncio.Future[float] = asyncio.get_running_loop().create_future()
        self._waiters.append(waiter)
        return await waiter

    def insert(self) -> None:
        self._inserted = True

    def pull(self) -> None:
        """Pull the cord: wake the waiters with the time of the pull, if it was in place."""
        if not self._inserted:
            return
        self._inserted = False
        waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(self._clock.now())
