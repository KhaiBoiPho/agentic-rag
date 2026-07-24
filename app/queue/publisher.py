"""RabbitMQ publisher — enqueue document ingestion jobs."""
from __future__ import annotations

import json
import uuid

import aio_pika

from app.config import settings

INGEST_QUEUE = "ingest_jobs"


async def publish_ingest_job(
    kb_id: str,
    user_id: str,
    filename: str,
    content: bytes,
    config: dict,
    mode: str = "standard",
) -> str:
    job_id = str(uuid.uuid4())
    message = {
        "job_id": job_id,
        "kb_id": kb_id,
        "user_id": user_id,
        "filename": filename,
        "content_b64": __import__("base64").b64encode(content).decode(),
        "config": config,
        "mode": mode,
    }
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(INGEST_QUEUE, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=INGEST_QUEUE,
        )
    return job_id
