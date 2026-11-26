"""Wait with a deadline counted on the Clock port (ADR 0010, ADR 0014).

asyncio.timeout and asyncio.wait_for count in real time, which a fake clock never moves: every
bounded wait of the brain goes through until, the waits of a Watch included. It lives next to
Watch because the services and the adapters both need it and ignore each other (ADR 0008).
"""

import asyncio
from collections.abc import Awaitable

from dvb_brain.ports.clock import Clock


async def until[T](clock: Clock, awaitable: Awaitable[T], deadline: float) -> T | None:
    """Return the result of awaitable, or None once the clock reaches deadline (s).

    The awaitable never gives None. At the deadline, or when the caller is cancelled, the wait is
    cancelled, then awaited to its end: a cancelled move() has sent its stop and freed the port
    when until returns (ADR 0010). The cancellation of the caller goes on, as does an exception
    of the wait.
    """
    task = asyncio.ensure_future(awaitable)
    timer = asyncio.ensure_future(clock.sleep_until(deadline))
    try:
        await asyncio.wait((task, timer), return_when=asyncio.FIRST_COMPLETED)
    finally:
        timer.cancel()
        if not task.done():
            task.cancel()
            await asyncio.wait((task,))  # never raises: the cancellation of the caller goes on
    return None if task.cancelled() else task.result()
