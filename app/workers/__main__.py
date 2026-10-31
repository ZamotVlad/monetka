"""Background jobs: python -m app.workers"""

import asyncio
import logging
import signal

from aiokafka.errors import KafkaError
from prometheus_client import start_http_server

from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory
from app.integrations.storage import S3Storage
from app.messaging.kafka import KafkaPublisher
from app.observability import configure_logging
from app.workers import jobs
from app.workers.runner import every

logger = logging.getLogger("app.workers")


async def start_publisher(settings: Settings, stop: asyncio.Event) -> KafkaPublisher | None:
    delay = 1.0
    while not stop.is_set():
        publisher = KafkaPublisher(settings.kafka_bootstrap_servers)
        try:
            await publisher.start()
            return publisher
        except KafkaError as error:
            logger.warning("kafka unavailable (%s), retrying in %.0fs", error, delay)
            await publisher.stop()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    return None


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)

    storage = S3Storage(settings)
    await storage.ensure_bucket()
    start_http_server(9100)
    publisher = await start_publisher(settings, stop)
    try:
        if publisher is not None:
            await asyncio.gather(
                every(
                    "relay-outbox", 0.5, lambda: jobs.relay_outbox(session_factory, publisher), stop
                ),
                every(
                    "expire-payments",
                    5,
                    lambda: jobs.expire_payments(session_factory, settings),
                    stop,
                ),
                every(
                    "reconcile",
                    settings.reconciliation_interval_seconds,
                    lambda: jobs.reconcile(session_factory),
                    stop,
                ),
                every(
                    "monthly-statements",
                    3600,
                    lambda: jobs.monthly_statements(session_factory, storage),
                    stop,
                ),
            )
    finally:
        if publisher is not None:
            await publisher.stop()
        await engine.dispose()


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    asyncio.run(main())
