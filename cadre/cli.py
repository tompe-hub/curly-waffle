"""Command line entry points.

    cadre init            create the database and load the seed watchlist
    cadre run             the daily job (this is what cron calls)
    cadre reextract       replay extraction over the archive after a rule change
    cadre check-source    diagnose a source's selectors against live HTML
    cadre serve           start the dashboard
    cadre stats           one-screen summary of database state
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

from cadre import db
from cadre.config import Config
from cadre.pipeline import reextract, run_daily
from cadre.sources import ALL_SOURCES, ENABLED_SOURCES, Fetcher

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _fetcher(cfg: Config) -> Fetcher:
    return Fetcher(
        user_agent=cfg.user_agent,
        timeout=cfg.request_timeout,
        delay=cfg.delay_between_requests,
        offline=cfg.offline,
        fixture_dir=FIXTURE_DIR,
    )


def cmd_init(args, cfg: Config) -> int:
    cfg.ensure_dirs()
    conn = db.connect(cfg.db_path)
    db.migrate(conn)
    seed = Path(args.seed)
    added = 0
    if seed.exists():
        with seed.open(encoding="utf-8") as fh:
            rows = csv.DictReader(line for line in fh if not line.startswith("#"))
            for row in rows:
                cur = conn.execute(
                    "INSERT INTO person (name_zh, name_pinyin, notes) VALUES (?, ?, ?)",
                    (row["name_zh"], row.get("name_pinyin"), row.get("note")),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO watchlist (person_id, tier, note) VALUES (?, ?, ?)",
                    (cur.lastrowid, int(row.get("tier") or 3), row.get("note")),
                )
                added += 1
        conn.commit()
    print(f"database ready at {cfg.db_path}; {added} people seeded")
    return 0


def cmd_run(args, cfg: Config) -> int:
    conn = db.connect(cfg.db_path)
    db.migrate(conn)
    sources = ENABLED_SOURCES
    if args.source:
        sources = [s for s in ALL_SOURCES if s.id == args.source]
        if not sources:
            print(f"unknown source: {args.source}", file=sys.stderr)
            return 2
    with _fetcher(cfg) as fetcher:
        report = run_daily(conn, cfg, fetcher, sources=sources)
    for sr in report.sources:
        line = f"  {sr.source_id:<14} {sr.status:<7} seen={sr.docs_seen} new={sr.docs_new} signals={sr.signals}"
        if sr.error:
            line += f"  !! {sr.error}"
        print(line)
    print(f"run {report.run_id}: {report.status}")
    return 0 if report.status == "ok" else 1


def cmd_reextract(args, cfg: Config) -> int:
    conn = db.connect(cfg.db_path)
    db.migrate(conn)
    n = reextract(conn, cfg, source_id=args.source)
    print(f"re-extracted archive: {n} new signals")
    return 0


def cmd_check_source(args, cfg: Config) -> int:
    """Fetch a source's listing pages and report what the selectors matched.

    This is the tool for verifying the CCDI selectors against the live site --
    they were written from the shapes these CMS pages have historically used and
    have not been confirmed against a real fetch."""
    source = next((s for s in ALL_SOURCES if s.id == args.source), None)
    if source is None:
        print(f"unknown source: {args.source}", file=sys.stderr)
        return 2
    with _fetcher(cfg) as fetcher:
        for url in source.listing_urls():
            try:
                html = fetcher.get(url)
            except Exception as exc:
                print(f"  {url}\n    FETCH FAILED: {type(exc).__name__}: {exc}")
                continue
            links = source.parse_listing(html, url)
            print(f"  {url}\n    {len(html)} bytes, {len(links)} links parsed")
            for link in links[:5]:
                print(f"      [{link.published_at or '????-??-??'}] {link.title[:60]}")
                print(f"        {link.url}")
            if not links:
                print("    NO LINKS -- selectors need updating (see cadre/sources/ccdi.py)")
    return 0


def cmd_serve(args, cfg: Config) -> int:
    import uvicorn
    uvicorn.run("cadre.web.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_stats(args, cfg: Config) -> int:
    conn = db.connect(cfg.db_path)
    db.migrate(conn)
    q = lambda sql: conn.execute(sql).fetchone()[0]
    print(f"people          {q('SELECT COUNT(*) FROM person')}")
    print(f"watchlist       {q('SELECT COUNT(*) FROM watchlist')}")
    print(f"documents       {q('SELECT COUNT(*) FROM document')}")
    resolved = q("SELECT COUNT(*) FROM signal WHERE resolution = 'resolved'")
    needs_review = q("SELECT COUNT(*) FROM signal WHERE resolution != 'resolved'")
    unreviewed = q("SELECT COUNT(*) FROM event WHERE review_state = 'new'")
    print(f"signals         {q('SELECT COUNT(*) FROM signal')}")
    print(f"  resolved      {resolved}")
    print(f"  needs review  {needs_review}")
    print(f"events          {q('SELECT COUNT(*) FROM event')}")
    print(f"  unreviewed    {unreviewed}")
    print(f"runs            {q('SELECT COUNT(*) FROM run')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cadre", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create database and seed the watchlist")
    p.add_argument("--seed", default="seed/watchlist.csv")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("run", help="run the daily job")
    p.add_argument("--source", help="limit to one source id")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("reextract", help="replay extraction over the archive")
    p.add_argument("--source")
    p.set_defaults(func=cmd_reextract)

    p = sub.add_parser("check-source", help="diagnose a source's selectors")
    p.add_argument("source")
    p.set_defaults(func=cmd_check_source)

    p = sub.add_parser("serve", help="start the dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("stats", help="database summary")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    return args.func(args, Config.load())


if __name__ == "__main__":
    raise SystemExit(main())
