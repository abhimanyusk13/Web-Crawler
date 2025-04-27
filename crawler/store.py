import os
import json
import asyncio
import hashlib
from datetime import datetime
from urllib.parse import urlparse

import aio_pika
import motor.motor_asyncio
from dotenv import load_dotenv

from crawler.parser import parse_html

# load environment variables from .env
load_dotenv()

# Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/news")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
RAW_QUEUE = os.getenv("RAW_PAGES_QUEUE", "raw_pages")


async def ensure_indexes(db):
    # ensure indexes for dedup and query patterns
    await db.articles.create_index("canonical_url")
    await db.articles.create_index("hash")
    await db.articles.create_index([("source", 1), ("published_at", -1)])


async def process_message(message: aio_pika.IncomingMessage):
    async with message.process():
        payload = json.loads(message.body)
        url = payload["url"]
        raw_html = payload["html"]
        fetched_time = payload["fetched_time"]

        # parse the HTML into structured fields
        parsed = parse_html(raw_html, url)
        body_html = parsed["body"]

        # compute a content hash of the body for dedup
        content_hash = hashlib.md5(body_html.encode("utf-8")).hexdigest()

        canonical = parsed["canonical_url"]
        # extract news source domain
        source = urlparse(canonical).netloc

        # build the document
        doc = {
            "url": url,
            "canonical_url": canonical,
            "source": source,
            "title": parsed["title"],
            "body": body_html,
            "author": parsed.get("author"),
            "tags": parsed.get("tags", []),
            "published_at": parsed.get("published_at"),
            "fetched_at": fetched_time,
            "hash": content_hash,
            "updated": datetime.utcnow().isoformat() + "Z",
        }

        # upsert: only insert or update if hash differs
        await process_message.db.articles.update_one(
            {"canonical_url": canonical, "hash": content_hash},
            {"$set": doc},
            upsert=True
        )


async def main():
    # connect to MongoDB
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = client.get_default_database()
    await ensure_indexes(db)

    # connect to RabbitMQ
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    queue = await channel.declare_queue(RAW_QUEUE, durable=True)

    # attach db to the message handler
    process_message.db = db

    print(" [*] Waiting for messages. To exit press CTRL+C")
    await queue.consume(process_message)

    # keep the service running
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())


'''
Dependencies:
[tool.poetry.dependencies]
motor = "^3.1"
aio-pika = "^6.8"
python-dotenv = "^1.0.0"
readability-lxml = "^0.8.1"
lxml = "*"


.env 
MONGO_URI=mongodb://mongo:27017/news
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
RAW_PAGES_QUEUE=raw_pages

bash command:
python -m crawler.store
'''