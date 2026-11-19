"""Start cord port: the only way a match starts (RG F.6)."""

from typing import Protocol


class StartSwitchPort(Protocol):
    def inserted(self) -> bool:
        """Tell whether the start cord is in place."""
        ...

    async def wait_pulled(self) -> float:
        """Wait for the next pull of the cord after the call and return its time on the Clock.

        The time is the one of the first raw edge, not the end of the debounce: it is the t0 of
        the match (RG H.2). A cord already out does not count. No timeout: the wait of an armed
        robot has no bound, disarming cancels it. Reading the cord only when armed is the job
        of the match manager (RG F.6, H.4).
        """
        ...
