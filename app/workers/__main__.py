"""Background jobs: python -m app.workers"""

import asyncio
import logging
import signal

from app.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.workers import jobs
from app.workers.runner import every


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    try:
        await asyncio.gather(
            every(
                "expire-payments", 5, lambda: jobs.expire_payments(session_factory, settings), stop
            ),
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
