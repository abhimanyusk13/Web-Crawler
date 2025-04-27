import os
import sys
import argparse
import asyncio
import json
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
import aio_pika
from dotenv import load_dotenv

from crawler.seed import load_seeds

# load .env into os.environ
load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE_NAME = os.getenv("RAW_PAGES_QUEUE", "raw_pages")


class DomainRateLimiter:
    def __init__(self, interval: float):
        self.interval = interval
        self.locks: dict[str, asyncio.Lock] = {}
        self.last_called: dict[str, float] = {}

    def _get_lock(self, domain: str) -> asyncio.Lock:
        if domain not in self.locks:
            self.locks[domain] = asyncio.Lock()
            self.last_called[domain] = 0.0
        return self.locks[domain]

    async def throttle(self, domain: str):
        lock = self._get_lock(domain)
        async with lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self.last_called[domain]
            wait = self.interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            # update timestamp after waiting
            self.last_called[domain] = asyncio.get_event_loop().time()


async def fetch_and_publish(
    url: str,
    session: aiohttp.ClientSession,
    rate_limiter: DomainRateLimiter,
    exchange: aio_pika.Exchange,
    max_retries: int = 3,
):
    parsed = urlparse(url)
    domain = parsed.netloc or url
    for attempt in range(1, max_retries + 1):
        try:
            await rate_limiter.throttle(domain)
            async with session.get(url, timeout=10) as resp:
                status = resp.status
                content = await resp.text()
            if status != 200:
                print(f"non-200 status {status} for {url}", file=sys.stderr)
                return
            ts = datetime.utcnow().isoformat() + "Z"
            message = {
                "url": url,
                "html": content,
                "fetched_time": ts,
            }
            body = json.dumps(message).encode()
            await exchange.publish(
                aio_pika.Message(
                    body=body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=QUEUE_NAME,
            )
            print(f"fetched: {url}")
            return
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"error fetching {url} (attempt {attempt}): {e}", file=sys.stderr)
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
            else:
                print(f"failed to fetch {url} after {max_retries} attempts", file=sys.stderr)


async def main(max_urls: int, concurrency: int, rate_interval: float):
    seeds = load_seeds()
    # flatten all URLs from rss, sitemap, sections
    urls = []
    for entry in seeds.values():
        for v in entry.values():
            if isinstance(v, list):
                urls.extend(v)
            else:
                urls.append(v)

    if not urls:
        print("no seeds found; add some with the seed CLI", file=sys.stderr)
        return

    urls = urls[:max_urls]

    # connect to RabbitMQ
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    # ensure the queue exists
    await channel.declare_queue(QUEUE_NAME, durable=True)
    exchange = channel.default_exchange

    rate_limiter = DomainRateLimiter(rate_interval)
    sem = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession(headers={"User-Agent": "news-crawler/0.1"}) as session:
        tasks = []
        for url in urls:
            await sem.acquire()
            task = asyncio.create_task(
                fetch_and_publish(url, session, rate_limiter, exchange)
            )
            task.add_done_callback(lambda t: sem.release())
            tasks.append(task)
        await asyncio.gather(*tasks)

    await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Async fetcher: enqueue raw pages")
    parser.add_argument(
        "--max",
        type=int,
        default=100,
        help="maximum number of URLs to fetch",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="maximum concurrent fetches",
    )
    parser.add_argument(
        "--rate-interval",
        type=float,
        default=2.0,
        help="seconds between requests per domain",
    )
    args = parser.parse_args()
    asyncio.run(main(args.max, args.concurrency, args.rate_interval))


'''
Example usage:
poetry add aio-pika

.env should contain:
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
RAW_PAGES_QUEUE=raw_pages

bash command:
poetry run python -m crawler.fetch_async --max 50 --concurrency 10 --rate-interval 2.0
'''