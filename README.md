# News Crawler & Search Engine

A zero-cost, end-to-end pipeline that:

1. **Crawls** configurable news seeds (RSS, sitemaps, section URLs)  
2. **Fetches** pages asynchronously with per-domain rate limiting  
3. **Parses** and cleans article HTML into structured JSON  
4. **Deduplicates** via content hashes  
5. **Stores** into MongoDB Atlas (free M0)  
6. **Indexes** into Typesense (self-hosted on a micro VM) with both BM25 and 384-dim embeddings  
7. **Exposes** a FastAPI search gateway (keyword, semantic, personalized ranking)  
8. **Schedules** periodic crawl runs via GitHub Actions cron  
9. **CI/CD** via GitHub Actions (lint, test, build, push Docker image)  

---

## Table of Contents

- [Prerequisites](#prerequisites)  
- [Getting Started](#getting-started)  
- [Services & Commands](#services--commands)  
- [CI/CD & Scheduler](#cicd--scheduler)  
- [Deployment](#deployment)  
- [Further Work](#further-work)  

---

## Prerequisites

- Docker & Docker Compose  
- Python 3.12 & Poetry  
- MongoDB Atlas free cluster (M0)  
- A Typesense instance (self-hosted on t2.micro or Fly.io)  
- GitHub repo with Secrets set:  
  - `MONGO_URI`  
  - `RABBITMQ_URL`  
  - `TYPESENSE_API_KEY`  

---

## Getting Started

1. **Clone & configure**  
   ```bash
   git clone https://github.com/you/news-crawler.git
   cd news-crawler
   cp .env.example .env
   # edit .env with your connection strings & API keys
   ```
2. **Install dependencies**  
   ```bash
   poetry install
   ```
3. **Build & launch all services**  
   ```bash
   docker-compose up -d
   ```
4. **Verify**  
   - `docker ps` shows services: fetcher, store, indexer, api, mongo, rabbitmq, typesense  
   - Health check:  
     ```bash
     curl http://localhost:8000/health
     ```
   - Swagger UI:  
     [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Services & Commands

### Seed Loader

Manage your seed definitions in `seeds.yml`:

- **Add a source**  
  ```bash
  python -m crawler.seed add reuters \
    --rss https://www.reuters.com/rssFeed/topNews \
    --sitemap https://www.reuters.com/sitemap_index.xml \
    --section https://www.reuters.com/world
  ```
- **List sources**  
  ```bash
  python -m crawler.seed ls
  ```
- **Remove a source**  
  ```bash
  python -m crawler.seed rm reuters
  ```

### Async Fetcher

Fetch raw pages and enqueue them:

```bash
poetry run python -m crawler.fetch_async --max 100 --concurrency 10 --rate-interval 2.0
```

### Store Worker

Parse raw pages and upsert into MongoDB:

```bash
poetry run python -m crawler.store
```

### Indexer

Incrementally index MongoDB documents into Typesense (includes embeddings):

```bash
poetry run python -m crawler.indexer
```

### API Gateway

Expose keyword, semantic, and personalized search:

```bash
uvicorn crawler.api:app --host 0.0.0.0 --port 8000
```

---

## CI/CD & Scheduler

- **CI**:  
  - Workflow: `.github/workflows/ci.yml`  
  - Runs on push/PR to `main`: lint (Black, isort), pytest, build & push Docker image to GHCR  

- **Scheduled Crawl**:  
  - Workflow: `.github/workflows/scheduled_crawl.yml`  
  - Cron: every 15 minutes → runs the async fetcher against your hosted services  

---

## Deployment

1. Push `main` → GitHub Actions builds & pushes `ghcr.io/you/news-crawler:latest`.  
2. On your VM or Fly.io instance, run:  
   ```bash
   docker-compose pull
   docker-compose up -d
   ```
3. Ensure public access & HTTPS via Fly.io certs or a reverse proxy (e.g. Cloudflare).

---

## Further Work

- **Personalization**: track user clicks → update a lightweight SQLite profile & blend in affinity scores  
- **Summarization**: integrate a small T5-based summarizer, cache in MongoDB  
- **Duplicate clustering**: add MinHash LSH to surface only the earliest copy among near-duplicates  
- **Trend detection**: ingest mention counts into Redis Timeseries (free cloud plan) and surface spikes  
- **Admin UI**: build a React dashboard to view crawl metrics, manage seeds, and preview articles