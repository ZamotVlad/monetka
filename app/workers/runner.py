import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

logger = logging.getLogger(__name__)

Job = Callable[[], Awaitable[object]]


async def every(name: str, interval: float, job: Job, stop: asyncio.Event) -> None:
    """Run a job on a fixed pause until asked to stop.

    One failed run is logged and the loop goes on: a database blip must not kill the worker.
    """
    while not stop.is_set():
        try:
            await job()
        except Exception:
            logger.exception("job %s failed", name)
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
