"""Clock of the robot: the monotonic time of the system, the one asyncio uses too."""

import asyncio
import time


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, dt: float) -> None:
        await asyncio.sleep(dt)  # returns at once when dt <= 0

    async def sleep_until(self, t: float) -> None:
        await self.sleep(t - self.now())
