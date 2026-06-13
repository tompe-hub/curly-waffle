"""SQLite storage for fetched articles.

One table, ``articles``, keyed by a stable id (hash of the link) so re-fetching
the same item is an idempotent upsert. Tags are stored as a comma-separated
string for simple substring filtering.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    region      TEXT NOT NULL,
    title       TEXT NOT NULL,
    link        TEXT NOT NULL,
    summary     TEXT,
    published   TEXT,            -- ISO 8601 UTC, best-effort
    fetched_at  TEXT NOT NULL,   -- ISO 8601 UTC
    tags        TEXT NOT NULL    -- comma-separated, e.g. "ai,china"
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published);
"""


@dataclass
class Article:
    source: str
    region: str
    title: str
    link: str
    summary: str
    published: str | None
    tags: list[str]
    fetched_at: str | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = hashlib.sha256(self.link.encode("utf-8")).hexdigest()[:16]
        if self.fetched_at is None:
            self.fetched_at = datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: Path | str = DB_PATH):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def upsert_articles(articles: list[Article], db_path: Path | str = DB_PATH) -> int:
    """Insert new articles, ignoring ones already stored. Returns count inserted."""
    init_db(db_path)
    inserted = 0
    with connect(db_path) as conn:
        for a in articles:
            cur = conn.execute(
                """INSERT OR IGNORE INTO articles
                   (id, source, region, title, link, summary, published, fetched_at, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (a.id, a.source, a.region, a.title, a.link, a.summary,
                 a.published, a.fetched_at, ",".join(a.tags)),
            )
            inserted += cur.rowcount
    return inserted


def query_articles(
    tag: str | None = None,
    region: str | None = None,
    since: str | None = None,
    limit: int = 200,
    db_path: Path | str = DB_PATH,
) -> list[dict]:
    """Fetch articles, newest first, with optional tag/region/date filters."""
    init_db(db_path)
    sql = "SELECT * FROM articles WHERE 1=1"
    params: list = []
    if tag:
        sql += " AND (',' || tags || ',') LIKE ?"
        params.append(f"%,{tag},%")
    if region:
        sql += " AND region = ?"
        params.append(region)
    if since:
        sql += " AND COALESCE(published, fetched_at) >= ?"
        params.append(since)
    sql += " ORDER BY COALESCE(published, fetched_at) DESC LIMIT ?"
    params.append(limit)

    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = [t for t in d["tags"].split(",") if t]
        result.append(d)
    return result


def tag_counts(since: str | None = None, db_path: Path | str = DB_PATH) -> dict[str, int]:
    """Count articles per tag (optionally since a date)."""
    init_db(db_path)
    counts = {"ai": 0, "quantum": 0, "china": 0, "total": 0}
    sql = "SELECT tags FROM articles"
    params: list = []
    if since:
        sql += " WHERE COALESCE(published, fetched_at) >= ?"
        params.append(since)
    with connect(db_path) as conn:
        for (tags,) in conn.execute(sql, params).fetchall():
            counts["total"] += 1
            for t in tags.split(","):
                if t in counts:
                    counts[t] += 1
    return counts
