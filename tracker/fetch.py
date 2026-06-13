"""Fetch RSS/Atom feeds, classify items, and store them.

Run directly to refresh the database::

    python -m tracker.fetch

Network failures on individual feeds are caught and logged so one dead feed
never breaks a refresh.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import feedparser
import requests

from .classify import classify
from .feeds import Feed, load_feeds
from .store import Article, upsert_articles

log = logging.getLogger(__name__)

USER_AGENT = "curly-waffle-tracker/0.1 (+https://github.com/tompe-hub/curly-waffle)"
HTTP_TIMEOUT = 20


class FeedError(RuntimeError):
    """Raised when a feed cannot be fetched (network, HTTP, or egress block)."""


def _to_iso(entry) -> str | None:
    """Best-effort published timestamp as ISO 8601 UTC."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc).isoformat()
    return None


def _clean_summary(entry, limit: int = 600) -> str:
    raw = entry.get("summary", "") or ""
    # Strip tags crudely; the dashboard renders text, not HTML.
    import re

    text = re.sub(r"<[^>]+>", "", raw).strip()
    return text[:limit]


def _download(url: str) -> bytes:
    """Fetch raw feed bytes, surfacing HTTP/egress errors clearly.

    Fetching with ``requests`` (rather than letting feedparser fetch) means an
    egress-allowlist block (HTTP 403 with a plain-text body) raises a readable
    FeedError instead of feedparser's opaque "syntax error" on the block page.
    """
    resp = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
    if resp.status_code == 403 and "allowlist" in resp.text.lower():
        raise FeedError(f"blocked by network egress allowlist ({resp.url})")
    if resp.status_code >= 400:
        raise FeedError(f"HTTP {resp.status_code}")
    return resp.content


def fetch_feed(feed: Feed) -> list[Article]:
    """Parse one feed into classified Article objects."""
    parsed = feedparser.parse(_download(feed.url))
    if parsed.bozo and not parsed.entries:
        raise FeedError(str(getattr(parsed, "bozo_exception", "unparseable feed")))

    articles: list[Article] = []
    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        summary = _clean_summary(entry)
        tags = classify(title, summary, feed.region, feed.tags)
        articles.append(
            Article(
                source=feed.name,
                region=feed.region,
                title=title,
                link=link,
                summary=summary,
                published=_to_iso(entry),
                tags=tags,
            )
        )
    return articles


def refresh(feeds: list[Feed] | None = None) -> dict:
    """Fetch all feeds and store new items. Returns a summary dict."""
    feeds = feeds if feeds is not None else load_feeds()
    all_articles: list[Article] = []
    per_feed: dict[str, int] = {}
    failures: dict[str, str] = {}

    for feed in feeds:
        try:
            items = fetch_feed(feed)
            per_feed[feed.name] = len(items)
            all_articles.extend(items)
        except Exception as exc:  # noqa: BLE001 - never let one feed kill the run
            log.warning("Error fetching %s: %s", feed.name, exc)
            failures[feed.name] = str(exc)

    inserted = upsert_articles(all_articles)
    return {
        "feeds": len(feeds),
        "items_seen": len(all_articles),
        "inserted": inserted,
        "failures": failures,
        "per_feed": per_feed,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = refresh()
    print(
        f"Fetched {summary['feeds']} feeds, "
        f"saw {summary['items_seen']} items, "
        f"inserted {summary['inserted']} new."
    )
    if summary["failures"]:
        print("\nFeeds that failed:")
        for name, reason in summary["failures"].items():
            print(f"  - {name}: {reason}")


if __name__ == "__main__":
    main()
