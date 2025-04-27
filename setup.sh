# 1. Create the folder structure
mkdir -p news-crawler/crawler
cd news-crawler

# 2. Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y build-essential git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

WORKDIR /app
COPY pyproject.toml poetry.lock* /app/

RUN poetry config virtualenvs.create false \
    && poetry install --no-root --no-interaction --no-ansi

COPY . /app
CMD ["tail", "-f", "/dev/null"]
EOF

# 3. docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: "3.8"
services:
  crawler:
    build: .
    container_name: news-crawler
    env_file:
      - .env
    depends_on:
      - mongo
      - rabbitmq
      - typesense
    volumes:
      - .:/app
    command: tail -f /dev/null

  mongo:
    image: mongo:6.0
    container_name: news-mongo
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db

  rabbitmq:
    image: rabbitmq:3-management
    container_name: news-rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest

  typesense:
    image: typesense/typesense:0.26.0
    container_name: news-typesense
    ports:
      - "8108:8108"
    env_file:
      - .env
    command: >
      --data-dir /data
      --api-key ${TYPESENSE_API_KEY}
      --listen-port 8108

volumes:
  mongo_data:
EOF

# 4. .env.example
cat > .env.example << 'EOF'
# MongoDB
MONGO_URI=mongodb://mongo:27017/news

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# Typesense
TYPESENSE_API_KEY=your_typesense_api_key_here
TYPESENSE_HOST=typesense
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http

# FastAPI
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
EOF

# 5. pyproject.toml
cat > pyproject.toml << 'EOF'
[tool.poetry]
name = "news-crawler"
version = "0.1.0"
description = "Skeleton for news‐crawler pipeline"
authors = ["Your Name <you@example.com>"]
readme = "README.md"
license = "MIT"

[tool.poetry.dependencies]
python = "^3.12"
aiohttp = "^3.8"
readability-lxml = "^0.8.1"
motor = "^3.1"
fastapi = "^0.100.0"
uvicorn = "^0.24.0"
typesense = "^1.0.0"
sentence-transformers = "^2.2.2"
PyYAML = "^6.0"
python-dotenv = "^1.0.0"

[tool.poetry.dev-dependencies]
pytest = "^7.0"
black = "^23.3.0"
isort = "^5.10.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
EOF

# 6. crawler/__init__.py
touch crawler/__init__.py

# 7. crawler/seed.py
cat > crawler/seed.py << 'EOF'
import os
import sys
import argparse
from pathlib import Path

import yaml

SEED_FILE = Path(os.getenv("SEED_FILE", "seeds.yml"))

def load_seeds() -> dict:
    if not SEED_FILE.exists():
        return {}
    data = yaml.safe_load(SEED_FILE.read_text())
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"Error: `{SEED_FILE}` must contain a top-level mapping.", file=sys.stderr)
        sys.exit(1)
    return data

def save_seeds(seeds: dict) -> None:
    SEED_FILE.write_text(yaml.safe_dump(seeds, sort_keys=False))

def cmd_add(args):
    seeds = load_seeds()
    name = args.name
    if name in seeds:
        print(f"Seed '{name}' already exists.", file=sys.stderr)
        sys.exit(1)
    entry = {}
    if args.rss:
        entry["rss"] = args.rss
    if args.sitemap:
        entry["sitemap"] = args.sitemap
    if args.sections:
        entry["sections"] = args.sections
    if not entry:
        print("You must supply at least one of --rss, --sitemap or --section.", file=sys.stderr)
        sys.exit(1)
    seeds[name] = entry
    save_seeds(seeds)
    print(f"Added seed '{name}'.")

def cmd_rm(args):
    seeds = load_seeds()
    name = args.name
    if name not in seeds:
        print(f"Seed '{name}' not found.", file=sys.stderr)
        sys.exit(1)
    del seeds[name]
    save_seeds(seeds)
    print(f"Removed seed '{name}'.")

def cmd_ls(_args):
    seeds = load_seeds()
    if not seeds:
        print("No seeds defined in seeds.yml.")
        return
    for name, entry in seeds.items():
        print(f"- {name}:")
        for k, v in entry.items():
            if isinstance(v, list):
                for item in v:
                    print(f"    {k}: {item}")
            else:
                print(f"    {k}: {v}")

def main():
    p = argparse.ArgumentParser(prog="seed", description="Manage your seeds.yml")
    sub = p.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a new seed source")
    p_add.add_argument("name", help="Unique key for this source")
    p_add.add_argument("--rss",     help="RSS feed URL")
    p_add.add_argument("--sitemap", help="Sitemap URL")
    p_add.add_argument(
        "--section",
        dest="sections",
        action="append",
        help="Section URL (can be used multiple times)"
    )
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("rm", help="Remove a seed source by name")
    p_rm.add_argument("name", help="Name of the source to remove")
    p_rm.set_defaults(func=cmd_rm)

    p_ls = sub.add_parser("ls", help="List all seed sources")
    p_ls.set_defaults(func=cmd_ls)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
EOF

# 8. seeds.yml (empty to start)
touch seeds.yml
