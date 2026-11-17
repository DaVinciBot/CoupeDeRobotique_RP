"""Clock port: the only way the brain reads or waits for time.

In simulation and in the tests, a fake clock plays a match in a few seconds, reproducibly
(architecture, section 5.3).
"""

from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Return the monotonic time, in s."""
        ...

    async def sleep(self, dt: float) -> None:
        """Wait dt seconds; return at once when dt <= 0."""
        ...

    async def sleep_until(self, t: float) -> None:
        """Wait until now() reaches t; return at once when t is already past."""
        ...
