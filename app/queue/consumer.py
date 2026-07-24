"""RabbitMQ consumer — processes ingestion jobs from the queue."""

from __future__ import annotations

import base64
import json
import logging

import aio_pika

from app.config import settings
from app.core.ingestion.pipeline import IngestionPipeline
from app.core.ingestion.price_pipeline import PriceExtractionPipeline
from app.queue.publisher import INGEST_QUEUE

logger = logging.getLogger(__name__)
_pipeline = IngestionPipeline()
_price_pipeline = PriceExtractionPipeline()


async def start_consumer() -> None:
    logger.info("Starting RabbitMQ consumer on queue=%s", INGEST_QUEUE)
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=4)
    queue = await channel.declare_queue(INGEST_QUEUE, durable=True)

    async with queue.iterator() as q:
        async for message in q:
            async with message.process(requeue=True):
                try:
                    body = json.loads(message.body)
                    content = base64.b64decode(body["content_b64"])
                    mode = body.get("mode")
                    pipeline = _price_pipeline if mode == "price_extraction" else _pipeline
                    async for _ in pipeline.ingest_stream(
                        job_id=body["job_id"],
                        kb_id=body["kb_id"],
                        user_id=body["user_id"],
                        filename=body["filename"],
                        content=content,
                        config=body.get("config", {}),
                    ):
                        pass
                except Exception:
                    logger.exception("Ingestion job failed job_id=%s", body.get("job_id"))
