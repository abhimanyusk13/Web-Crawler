# File: crawler/indexer.py
#!/usr/bin/env python3
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

import typesense
import motor.motor_asyncio
import asyncio
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

# Configuration
MONGO_URI        = os.getenv("MONGO_URI", "mongodb://localhost:27017/news")
TYPESENSE_HOST   = os.getenv("TYPESENSE_HOST", "localhost")
TYPESENSE_PORT   = int(os.getenv("TYPESENSE_PORT", "8108"))
TYPESENSE_PROTO  = os.getenv("TYPESENSE_PROTOCOL", "http")
TYPESENSE_KEY    = os.getenv("TYPESENSE_API_KEY", "")
LAST_INDEXED     = Path(os.getenv("LAST_INDEXED_FILE", ".last_indexed"))
POLL_INTERVAL    = int(os.getenv("INDEXER_INTERVAL", "60"))  # seconds

# Load embedder
EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

# Typesense collection schema with `vec`
COLLECTION_SCHEMA = {
    "name": "news",
    "fields": [
        {"name": "id",            "type": "string"},
        {"name": "title",         "type": "string"},
        {"name": "body",          "type": "string"},
        {"name": "source",        "type": "string",    "facet": True},
        {"name": "tags",          "type": "string[]",  "facet": True},
        {"name": "published_at",  "type": "int64",      "facet": True},
        {"name": "vec",           "type": "float[]",   "num_dim": 384}
    ],
    "default_sorting_field": "published_at"
}

def load_last_indexed() -> str:
    if not LAST_INDEXED.exists():
        return ""
    return LAST_INDEXED.read_text().strip()


def save_last_indexed(ts: str):
    LAST_INDEXED.write_text(ts)


def iso_to_epoch(ts: str) -> int:
    dt = datetime.fromisoformat(ts.rstrip("Z"))
    return int(dt.timestamp())


async def run_indexer():
    # Mongo client
    m_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = m_client.get_default_database()
    col = db.articles

    # Typesense client
    ts_client = typesense.Client({
        "nodes": [{
            "host": TYPESENSE_HOST,
            "port": TYPESENSE_PORT,
            "protocol": TYPESENSE_PROTO
        }],
        "api_key": TYPESENSE_KEY,
        "connection_timeout_seconds": 2
    })

    # Ensure collection exists
    try:
        ts_client.collections["news"].retrieve()
    except typesense.exceptions.ObjectNotFound:
        ts_client.collections.create(COLLECTION_SCHEMA)

    last_ts = load_last_indexed()
    query = {"updated": {"$gt": last_ts}} if last_ts else {}
    cursor = col.find(query).sort("updated", 1)

    docs_to_index = []
    new_last_ts = last_ts

    async for doc in cursor:
        ts_doc = {
            "id": str(doc["_id"]),
            "title": doc.get("title", ""),
            "body": doc.get("body", ""),
            "source": doc.get("source", ""),
            "tags": doc.get("tags", []),
            "published_at": iso_to_epoch(doc.get("published_at"))
                if doc.get("published_at") else 0
        }
        # compute embedding
        text = ts_doc["title"] + "\n" + ts_doc["body"]
        vec = EMBED_MODEL.encode(text, normalize_embeddings=True).tolist()
        ts_doc["vec"] = vec

        docs_to_index.append(ts_doc)
        new_last_ts = doc["updated"]

        if len(docs_to_index) >= 500:
            payload = "\n".join(json.dumps(d) for d in docs_to_index)
            ts_client.collections["news"].documents.import_(payload, {"action": "upsert"})
            docs_to_index = []

    if docs_to_index:
        payload = "\n".join(json.dumps(d) for d in docs_to_index)
        ts_client.collections["news"].documents.import_(payload, {"action": "upsert"})

    if new_last_ts and new_last_ts != last_ts:
        save_last_indexed(new_last_ts)


if __name__ == "__main__":
    try:
        while True:
            asyncio.run(run_indexer())
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        sys.exit(0)



'''
poetry add typesense

.env 
MONGO_URI=mongodb://mongo:27017/news
TYPESENSE_HOST=typesense
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=your_typesense_api_key_here
LAST_INDEXED_FILE=.last_indexed
INDEXER_INTERVAL=60

docker-compose up -d indexer
'''