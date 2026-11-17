"""Clock of the tests: time only moves when the test calls advance().

The time is counted in whole nanoseconds: a task that sleeps 0.05 s in a loop wakes exactly 20
times a second, where floats would drift (1.0000000000000002 is past 1.0).
"""

import asyncio
import heapq
import itertools
from collections.abc import Sized

_NS_PER_S = 1_000_000_000

# Loop turns a single settle may take before a task is declared to never block.
_MAX_SETTLE_TURNS = 10_000


def _to_ns(t: float) -> int:
    return round(t * _NS_PER_S)


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now_ns = _to_ns(start)
        self._sleepers: list[tuple[int, int, asyncio.Future[None]]] = []
        self._order = itertools.count()  # first come, first served at the same deadline

    def now(self) -> float:
        return self._now_ns / _NS_PER_S

    async def sleep(self, dt: float) -> None:
        await self._sleep_until_ns(self._now_ns + _to_ns(dt))

    async def sleep_until(self, t: float) -> None:
        deadline_ns = _to_ns(t)
        if deadline_ns / _NS_PER_S < t:  # never wake before t, even by a rounding
            deadline_ns += 1
        await self._sleep_until_ns(deadline_ns)

    async def _sleep_until_ns(self, deadline_ns: int) -> None:
        if deadline_ns <= self._now_ns:
            await asyncio.sleep(0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._sleepers, (deadline_ns, next(self._order), future))
        await future

    async def advance(self, dt: float) -> None:
        """Move the time dt seconds forward and wake the sleepers in deadline order.

        now() is set to each deadline in turn, and the woken tasks run until they block again
        before the next deadline: a periodic task wakes once per period within the window.
        """
        if dt < 0:
            raise ValueError(f"cannot go back in time: dt = {dt}")
        target_ns = self._now_ns + _to_ns(dt)
        await _settle()  # a task created just before sleeps from the time before the jump
        while self._sleepers and self._sleepers[0][0] <= target_ns:
            deadline_ns, _, future = heapq.heappop(self._sleepers)
            self._now_ns = deadline_ns
            if not future.done():  # a cancelled sleeper leaves a cancelled future
                future.set_result(None)
            await _settle()
        self._now_ns = target_ns


async def _settle() -> None:
    """Let every ready task run until it blocks again.

    asyncio has no public way to know that all tasks are blocked. The ready queue of the event
    loop (loop._ready, private but there since Python 3.4) holds the callbacks that can run; it
    is empty once every task waits on something. A fixed number of turns would let a long chain
    of tasks read a time that has already moved on, without any error.
    """
    ready: Sized | None = getattr(asyncio.get_running_loop(), "_ready", None)
    if ready is None:
        raise RuntimeError("FakeClock needs the ready queue of the asyncio event loop (_ready)")
    for _ in range(_MAX_SETTLE_TURNS):
        await asyncio.sleep(0)
        if len(ready) == 0:
            return
    raise RuntimeError(f"a task never blocks: still running after {_MAX_SETTLE_TURNS} turns")
