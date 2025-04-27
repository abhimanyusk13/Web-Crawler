from datetime import datetime
from typing import Optional

from readability import Document
from lxml import html

def _extract_meta(tree: html.HtmlElement, attr: str, value: str) -> Optional[str]:
    el = tree.xpath(f"//meta[@{attr}='{value}']/@content")
    return el[0].strip() if el else None

def _parse_datetime(dt_str: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.fromisoformat(dt_str) if "T" in dt_str else datetime.strptime(dt_str, fmt)
        except Exception:
            continue
    return None

def parse_html(raw_html: str, url: str) -> dict:
    """
    Input:
      - raw_html: full HTML text of the page
      - url: the requested URL (used as fallback canonical URL)

    Returns a dict with:
      - url
      - canonical_url
      - title
      - body        (HTML snippet of main content)
      - author      (str or None)
      - published_at (ISO8601 string or None)
    """
    # 1. Extract clean content + title
    doc = Document(raw_html)
    body_html = doc.summary()
    title = doc.title().strip()

    # 2. Build an lxml tree for metadata
    tree = html.fromstring(raw_html)

    # 3. Canonical URL
    canon = tree.xpath("//link[@rel='canonical']/@href")
    canonical_url = canon[0].strip() if canon else url

    # 4. Author
    author = (
        _extract_meta(tree, "name", "author")
        or _extract_meta(tree, "property", "article:author")
        or _extract_meta(tree, "name", "byl")
    )

    # 5. Published timestamp
    ts = (
        _extract_meta(tree, "property", "article:published_time")
        or _extract_meta(tree, "name", "pubdate")
        or _extract_meta(tree, "name", "publication_date")
        or _extract_meta(tree, "itemprop", "datePublished")
    )
    published_at = None
    if ts:
        dt = _parse_datetime(ts)
        if dt:
            # normalize to Zulu
            published_at = dt.isoformat() + "Z"

    return {
        "url": url,
        "canonical_url": canonical_url,
        "title": title,
        "body": body_html,
        "author": author,
        "published_at": published_at,
    }


'''
Example usage:
poetry add readability-lxml lxml
'''