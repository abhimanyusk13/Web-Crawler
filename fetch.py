#!/usr/bin/env python3
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from crawler.seed import load_seeds

DB_PATH = Path("raw_pages.db")

def init_db(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS raw_pages (
        url TEXT PRIMARY KEY,
        html TEXT NOT NULL,
        fetched_time TEXT NOT NULL
    )
    """)
    conn.commit()

def fetch_url(url: str, ua: str = "news-crawler/0.1") -> str:
    req = Request(url, headers={"User-Agent": ua})
    with urlopen(req, timeout=10) as resp:
        raw = resp.read()
        return raw.decode("utf-8", errors="replace")

def main():
    p = argparse.ArgumentParser(description="Sync fetcher: download pages into SQLite")
    p.add_argument("--max", type=int, default=10,
                   help="maximum number of URLs to fetch")
    args = p.parse_args()

    seeds = load_seeds()
    # flatten all URLs from rss, sitemap, sections
    urls = []
    for entry in seeds.values():
        for key, val in entry.items():
            if isinstance(val, list):
                urls.extend(val)
            else:
                urls.append(val)

    if not urls:
        print("No seeds found in seeds.yml. Please add some with the seed CLI.")
        return

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    fetched = 0
    for url in urls:
        if fetched >= args.max:
            break
        try:
            html = fetch_url(url)
        except (HTTPError, URLError, TimeoutError) as e:
            print(f"Error fetching {url!r}: {e}", file=sys.stderr)
            continue

        ts = datetime.utcnow().isoformat() + "Z"
        conn.execute(
            "REPLACE INTO raw_pages (url, html, fetched_time) VALUES (?, ?, ?)",
            (url, html, ts)
        )
        conn.commit()
        print(f"Fetched ({fetched+1}/{args.max}): {url}")
        fetched += 1

    conn.close()
    print(f"Done. {fetched} pages stored in {DB_PATH}")

if __name__ == "__main__":
    main()


'''
Example usage:
python -m crawler.seed add reuters --section https://www.reuters.com/world
python -m crawler.seed ls

poetry install

python fetch.py --max 10

sqlite3 raw_pages.db "SELECT url, fetched_time FROM raw_pages;"
'''