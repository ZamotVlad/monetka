import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

from app.messaging.events import TOPIC

logger = logging.getLogger(__name__)


class KafkaPublisher:
    def __init__(self, bootstrap_servers: str) -> None:
        # acks="all" + idempotence: a broker restart does not lose or double a message
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers, acks="all", enable_idempotence=True
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def publish(self, topic: str, key: str, value: bytes) -> None:
        await self._producer.send_and_wait(topic, value=value, key=key.encode())


Handler = Callable[[dict[str, Any]], Awaitable[None]]


async def consume_forever(bootstrap_servers: str, handler: Handler) -> None:
    """Feed every event to the handler; reconnect with backoff when Kafka is away.

    No consumer group: each API instance must see all events, because the user's
    WebSocket can be connected to any of them.
    """
    delay = 1.0
    while True:
        consumer = AIOKafkaConsumer(
            TOPIC, bootstrap_servers=bootstrap_servers, auto_offset_reset="latest"
        )
        try:
            await consumer.start()
            delay = 1.0
            async for message in consumer:
                try:
                    await handler(json.loads(message.value))
                except Exception:
                    logger.exception("event handler failed")
        except KafkaError as error:
            logger.warning("kafka unavailable (%s), retrying in %.0fs", error, delay)
        finally:
            await consumer.stop()
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
