"""Last value of a stream, and a notification on each new value.

A port gives its readings (motion status, lidar tracks…) through a Watch: a reader takes the
last value without waiting, or waits for the next one. Waits always have a timeout, counted on
the Clock port so that the tests stay reproducible with a fake clock.
"""

import asyncio
from collections.abc import Callable

from dvb_brain.ports.clock import Clock
from dvb_brain.ports.deadline import until


class Watch[T]:
    """Hold the last value only: values set while a reader is not running may be skipped.

    A value is never None: None means "no value yet" or "timeout".
    """

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._value: T | None = None
        self._waiters: list[asyncio.Future[T]] = []

    def set(self, value: T) -> None:
        """Store the value and give it to every waiting reader."""
        self._value = value
        waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(value)

    def get(self) -> T | None:
        """Return the last value, or None before the first one."""
        return self._value

    # ASYNC109 advises asyncio.timeout, which counts on the event loop clock: the timeouts of a
    # Watch count on the Clock port, so that a fake clock drives them.

    async def wait_next(self, timeout: float) -> T | None:  # noqa: ASYNC109
        """Return the next value set after the call, or None once timeout seconds are over."""
        return await self._next(self._clock.now() + timeout)

    async def wait_for(self, predicate: Callable[[T], bool], timeout: float) -> T | None:  # noqa: ASYNC109
        """Return the first value that matches, the current one included.

        Return None once timeout seconds are over.
        """
        deadline = self._clock.now() + timeout
        value = self._value
        while True:
            if value is not None and predicate(value):
                return value
            received = await self._next(deadline)
            if received is None:
                return None
            if predicate(received):
                return received
            value = self._value  # set again while this task was not running

    async def _next(self, deadline: float) -> T | None:
        """Return the value that wakes this reader, or None at the deadline."""
        waiter: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        self._waiters.append(waiter)
        try:
            return await until(self._clock, waiter, deadline)
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)  # no leak when the values stop coming
