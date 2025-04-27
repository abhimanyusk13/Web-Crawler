import os
from typing import Optional

import typesense
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Typesense configuration
TS_HOST     = os.getenv("TYPESENSE_HOST", "localhost")
TS_PORT     = int(os.getenv("TYPESENSE_PORT", "8108"))
TS_PROTO    = os.getenv("TYPESENSE_PROTOCOL", "http")
TS_API_KEY  = os.getenv("TYPESENSE_API_KEY", "")

# FastAPI configuration
FASTAPI_HOST = os.getenv("FASTAPI_HOST", "0.0.0.0")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", "8000"))

# Initialize Typesense client
ts_client = typesense.Client({
    "nodes": [{
        "host": TS_HOST,
        "port": TS_PORT,
        "protocol": TS_PROTO
    }],
    "api_key": TS_API_KEY,
    "connection_timeout_seconds": 2
})

app = FastAPI(title="News Search API", version="0.1.0")


class SearchResponse(BaseModel):
    found: int
    hits: list
    page: int
    request_params: dict
    search_time_ms: int
    cursor: Optional[str] = None


@app.get("/health")
def health():
    """
    Health check: verifies Typesense is reachable.
    """
    try:
        status = ts_client.health.retrieve()
        return {"typesense": status}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Typesense error: {e}")


@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Results per page"),
    cursor: Optional[str] = Query(None, description="Cursor for pagination")
):
    """
    Full-text search over title + body, sorted by published_at desc.
    """
    params = {
        "q": q,
        "query_by": "title,body",
        "sort_by": "published_at:desc",
        "per_page": limit,
    }
    if cursor:
        params["cursor"] = cursor

    try:
        result = ts_client.collections["news"].documents.search(params)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/latest", response_model=SearchResponse)
def latest(
    limit: int = Query(10, ge=1, le=100, description="Number of latest articles")
):
    """
    Return the most recent articles.
    """
    params = {
        "q": "*",
        "query_by": "title",
        "sort_by": "published_at:desc",
        "per_page": limit,
    }
    try:
        result = ts_client.collections["news"].documents.search(params)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/by-tag", response_model=SearchResponse)
def by_tag(
    tag: str = Query(..., description="Tag to filter by"),
    limit: int = Query(10, ge=1, le=100, description="Results per page"),
    cursor: Optional[str] = Query(None, description="Cursor for pagination")
):
    """
    Search for articles having the given tag.
    """
    filter_by = f"tags:=[{tag}]"
    params = {
        "q": "*",
        "query_by": "title",
        "filter_by": filter_by,
        "sort_by": "published_at:desc",
        "per_page": limit,
    }
    if cursor:
        params["cursor"] = cursor

    try:
        result = ts_client.collections["news"].documents.search(params)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

'''
.env
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000

docker-compose up -d api
curl http://localhost:8000/health
http://localhost:8000/docs
curl "http://localhost:8000/search?q=climate&limit=5"
'''