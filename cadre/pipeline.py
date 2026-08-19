"""The daily job.

    fetch -> archive -> extract -> resolve -> score -> cluster

Every stage is keyed on content hashes, so the whole run is idempotent: running
it twice in a day costs a few HTTP requests and changes nothing. That property
is what makes it safe to fix a parser and replay history through
`reextract()` rather than losing the events the old parser misread.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cadre import archive, cluster, score
from cadre.config import Config
from cadre.extract import EXTRACTOR_VERSION, extract_signals
from cadre.resolve import known_names, resolve_name
from cadre.sources import ENABLED_SOURCES, Fetcher, Source

log = logging.getLogger("cadre.pipeline")


@dataclass
class SourceReport:
    source_id: str
    status: str = "ok"
    docs_seen: int = 0
    docs_new: int = 0
    signals: int = 0
    error: str | None = None


@dataclass
class RunReport:
    run_id: int
    sources: list[SourceReport] = field(default_factory=list)
    events_new: int = 0
    status: str = "ok"

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "events_new": self.events_new,
            "sources": [s.__dict__ for s in self.sources],
        }


def run_daily(
    conn: sqlite3.Connection,
    cfg: Config,
    fetcher: Fetcher,
    *,
    sources: list[Source] | None = None,
    max_articles_per_source: int = 200,
) -> RunReport:
    sources = sources if sources is not None else ENABLED_SOURCES
    cfg.ensure_dirs()

    cur = conn.execute(
        "INSERT INTO run (started_at, status) VALUES (?, 'running')",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
    )
    report = RunReport(run_id=int(cur.lastrowid))
    conn.commit()

    names = known_names(conn)

    for source in sources:
        sr = SourceReport(source_id=source.id)
        try:
            _run_source(conn, cfg, fetcher, source, sr, names, report, max_articles_per_source)
        except Exception as exc:  # a broken source must not sink the whole run
            log.exception("source %s failed", source.id)
            sr.status = "error"
            sr.error = f"{type(exc).__name__}: {exc}"
        report.sources.append(sr)
        conn.execute(
            """INSERT INTO run_source (run_id, source_id, status, docs_seen, docs_new, error)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (report.run_id, sr.source_id, sr.status, sr.docs_seen, sr.docs_new, sr.error),
        )
        conn.commit()

    if any(s.status == "error" for s in report.sources):
        report.status = "partial"
    if report.sources and all(s.status == "error" for s in report.sources):
        report.status = "failed"

    conn.execute(
        "UPDATE run SET finished_at = ?, status = ?, stats_json = ? WHERE id = ?",
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            report.status,
            json.dumps(report.as_dict(), ensure_ascii=False),
            report.run_id,
        ),
    )
    conn.commit()
    return report


def _run_source(conn, cfg, fetcher, source, sr, names, report, max_articles):
    links = []
    for listing_url in source.listing_urls():
        html = fetcher.get(listing_url)
        found = source.parse_listing(html, listing_url)
        log.info("%s: %d links from %s", source.id, len(found), listing_url)
        links.extend(found)

    # Deduplicate across listing pages, preserving order.
    seen_urls: set[str] = set()
    unique = [l for l in links if not (l.url in seen_urls or seen_urls.add(l.url))]
    sr.docs_seen = len(unique)

    # Sanity guard, the same idea as the roster floor: a source that has
    # produced links before and now produces none is far more likely to have
    # been redesigned than to have gone quiet. Flag the run rather than
    # silently reporting "nothing happened today".
    if not unique and _source_had_links_before(conn, source.id):
        sr.status = "empty"
        sr.error = "listing returned no links but has before -- selectors may be stale"
        return

    for link in unique[:max_articles]:
        if _url_already_seen(conn, link.url):
            continue
        html = fetcher.get(link.url)
        doc = source.parse_article(html, link)
        if not doc.text:
            continue

        digest = archive.text_digest(doc.text)
        if _digest_already_seen(conn, digest):
            continue

        rel_path = archive.store(cfg.archive_dir, digest, doc.raw_html)
        doc_id = _insert_document(conn, doc, digest, rel_path)
        sr.docs_new += 1
        sr.signals += _extract_and_store(conn, doc_id, doc, names, report)
        conn.commit()


def _extract_and_store(conn, doc_id: int, doc, names: set[str], report: RunReport) -> int:
    signals = extract_signals(doc.text, doc.title, names)
    stored = 0

    for raw in signals:
        resolution = resolve_name(conn, raw.raw_name, raw.raw_position)
        person_id = resolution.person_id

        sig_score = score.significance(
            conn,
            kind=raw.kind,
            person_id=person_id,
            confidence=raw.confidence,
            name_is_guess=raw.name_is_guess,
            from_document=raw.from_document,
        )

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO signal
                (document_id, run_id, kind, person_id, raw_name, raw_position,
                 quoted_span, event_date, rule_id, confidence, resolution)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id, report.run_id, raw.kind, person_id, raw.raw_name,
                raw.raw_position, raw.quoted_span, doc.published_at,
                raw.rule_id, raw.confidence, resolution.status,
            ),
        )
        if not cur.rowcount:
            continue  # already extracted from this document
        signal_id = int(cur.lastrowid)
        stored += 1

        for cand_person, cand_score, method in resolution.candidates:
            conn.execute(
                """INSERT INTO resolution_candidate (signal_id, person_id, score, method)
                   VALUES (?, ?, ?, ?)""",
                (signal_id, cand_person, cand_score, method),
            )

        # Only resolved signals get clustered onto a person's event stream.
        # Ambiguous and unknown ones still create events -- keyed on the raw
        # name -- so they surface on the dashboard instead of vanishing into a
        # queue nobody reads.
        event_id = cluster.attach(
            conn,
            person_id=person_id,
            raw_name=None if person_id else raw.raw_name,
            kind=raw.kind,
            event_date=doc.published_at,
            summary=doc.title or raw.quoted_span[:120],
            significance=sig_score,
        )
        conn.execute("UPDATE signal SET event_id = ? WHERE id = ?", (event_id, signal_id))

    return stored


def reextract(conn: sqlite3.Connection, cfg: Config, source_id: str | None = None) -> int:
    """Replay extraction over archived documents.

    Run after changing the lexicon or the rules: the archive is the source of
    truth, the database is derived."""
    from cadre.sources.base import clean_text

    names = known_names(conn)
    sql = "SELECT * FROM document"
    params: tuple = ()
    if source_id:
        sql += " WHERE source_id = ?"
        params = (source_id,)

    cur = conn.execute("INSERT INTO run (started_at, status) VALUES (?, 'running')",
                       (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
    report = RunReport(run_id=int(cur.lastrowid))

    count = 0
    for row in conn.execute(sql, params).fetchall():
        raw_html = archive.load(cfg.archive_dir, row["archive_path"])
        doc = _DocView(
            source_id=row["source_id"], url=row["url"], title=row["title"] or "",
            published_at=row["published_at"], text=clean_text(raw_html), raw_html=raw_html,
        )
        count += _extract_and_store(conn, row["id"], doc, names, report)
        conn.execute(
            "UPDATE document SET extracted_at = datetime('now'), extractor_version = ? WHERE id = ?",
            (EXTRACTOR_VERSION, row["id"]),
        )
    conn.execute("UPDATE run SET finished_at = datetime('now'), status = 'ok' WHERE id = ?",
                 (report.run_id,))
    conn.commit()
    return count


@dataclass
class _DocView:
    source_id: str
    url: str
    title: str
    published_at: str | None
    text: str
    raw_html: str


# ------------------------------------------------------------------ queries --

def _url_already_seen(conn, url: str) -> bool:
    return conn.execute("SELECT 1 FROM document WHERE url = ? LIMIT 1", (url,)).fetchone() is not None


def _digest_already_seen(conn, digest: str) -> bool:
    return conn.execute("SELECT 1 FROM document WHERE sha256 = ? LIMIT 1", (digest,)).fetchone() is not None


def _source_had_links_before(conn, source_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM run_source WHERE source_id = ? AND docs_seen > 0 LIMIT 1", (source_id,)
    ).fetchone()
    return row is not None


def _insert_document(conn, doc, digest: str, rel_path: str) -> int:
    cur = conn.execute(
        """
        INSERT INTO document
            (sha256, source_id, url, title, published_at, fetched_at, archive_path,
             text_len, extracted_at, extractor_version)
        VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, datetime('now'), ?)
        """,
        (digest, doc.source_id, doc.url, doc.title, doc.published_at, rel_path,
         len(doc.text), EXTRACTOR_VERSION),
    )
    return int(cur.lastrowid)
