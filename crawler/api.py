# File: crawler/api.py
import os
import json
import sqlite3
from typing import Optional
from datetime import datetime

import typesense
from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from dotenv import load_dotenv

load_dotenv()

# Typesense configuration
TS_HOST    = os.getenv("TYPESENSE_HOST", "localhost")
TS_PORT    = int(os.getenv("TYPESENSE_PORT", "8108"))
TS_PROTO   = os.getenv("TYPESENSE_PROTOCOL", "http")
TS_API_KEY = os.getenv("TYPESENSE_API_KEY", "")

# FastAPI configuration
FASTAPI_HOST = os.getenv("FASTAPI_HOST", "0.0.0.0")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", "8000"))

# Initialize Typesense client
ts_client = typesense.Client({
    "nodes": [{"host": TS_HOST, "port": TS_PORT, "protocol": TS_PROTO}],
    "api_key": TS_API_KEY,
    "connection_timeout_seconds": 2
})
# Embedding model
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# Initialize FastAPI
app = FastAPI(title="News Search API", version="0.3.0")

# Metrics
REQUEST_COUNT = Counter(
    'api_request_count', 'Total API requests', ['method', 'endpoint', 'http_status']
)
REQUEST_LATENCY = Histogram(
    'api_request_latency_seconds', 'API request latency', ['endpoint']
)

# User profile SQLite DB
DB_PATH = os.getenv('USER_PROFILE_DB', 'user_profiles.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute(
    '''
    CREATE TABLE IF NOT EXISTS user_profile (
      user_id TEXT PRIMARY KEY,
      interest TEXT,
      cnt INTEGER,
      updated_at TEXT
    )
    '''
)
conn.commit()

class SearchResponse(BaseModel):
    found: int
    hits: list
    page: int
    request_params: dict
    search_time_ms: int
    cursor: Optional[str] = None

# Middleware for metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = datetime.utcnow()
    response = await call_next(request)
    latency = (datetime.utcnow() - start_time).total_seconds()
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(latency)
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path,
                         http_status=response.status_code).inc()
    return response

@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health():
    try:
        status = ts_client.health.retrieve()
        return {"typesense": status}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Typesense error: {e}")

@app.post("/click/{user_id}/{doc_id}")
def click(user_id: str, doc_id: str):
    # retrieve document vector from Typesense
    try:
        doc = ts_client.collections['news'].documents[doc_id].retrieve()
    except Exception:
        raise HTTPException(status_code=404, detail="Document not found")
    vec = doc.get('vec')
    if not vec:
        raise HTTPException(status_code=500, detail="Vector missing in document")

    cur = conn.cursor()
    cur.execute("SELECT interest, cnt FROM user_profile WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        old_interest, cnt = row
        old_vec = json.loads(old_interest)
        cnt += 1
        # incremental average
        new_vec = [(o*(cnt-1) + v)/cnt for o, v in zip(old_vec, vec)]
        cur.execute(
            "UPDATE user_profile SET interest = ?, cnt = ?, updated_at = ? WHERE user_id = ?",
            (json.dumps(new_vec), cnt, datetime.utcnow().isoformat()+'Z', user_id)
        )
    else:
        # first click
        cur.execute(
            "INSERT INTO user_profile (user_id, interest, cnt, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, json.dumps(vec), 1, datetime.utcnow().isoformat()+'Z')
        )
    conn.commit()
    return {"status": "ok"}

@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    semantic: bool = Query(False),
    user_id: Optional[str] = Query(None)
):
    # base search
    try:
        if semantic:
            q_vec = embed_model.encode(q, normalize_embeddings=True).tolist()
            params = {
                "q": "*",
                "query_by": "title",
                "vector_query": f"vec:([{','.join(map(str, q_vec))}], k:{limit})"
            }
        else:
            params = {
                "q": q,
                "query_by": "title,body",
                "sort_by": "published_at:desc",
                "per_page": limit
            }
            if cursor:
                params["cursor"] = cursor

        ts_result = ts_client.collections["news"].documents.search(params)
        hits = ts_result['hits']

        # personalization
        if user_id:
            cur = conn.cursor()
            cur.execute("SELECT interest FROM user_profile WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row:
                user_vec = json.loads(row[0])
                # vector search for user preference
                uv_param = {
                    "q": "*",
                    "query_by": "title",
                    "vector_query": f"vec:([{','.join(map(str, user_vec))}], k:{limit})"
                }
                uv_res = ts_client.collections["news"].documents.search(uv_param)
                user_scores = {r['document']['id']: r['vector_score'] for r in uv_res['hits']}
                # merge scores
                for hit in hits:
                    doc_id = hit['document']['id']
                    hit_score = hit['_ranking_score'] if '_ranking_score' in hit else 0
                    user_score = user_scores.get(doc_id, 0)
                    # weighted sum
                    hit['score'] = 0.8*hit_score + 0.2*user_score
                # sort hits
                hits.sort(key=lambda x: x['score'], reverse=True)
                ts_result['hits'] = hits
        return ts_result

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