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
from cadre.importers import import_roster, inspect_file
from cadre.pipeline import reextract, run_daily
from cadre.sources import ALL_SOURCES, ENABLED_SOURCES, Fetcher

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# display order for the import mapping report
FIELDS_ORDER = [
    "external_id", "name_zh", "name_pinyin", "birth_year", "birth_month",
    "sex", "native_place", "ethnicity", "cc_status", "rank",
    "org", "position_title", "start_date", "end_date",
]


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
    if args.no_seed:
        print(f"database ready at {cfg.db_path}; no seed loaded")
        return 0
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
    """Fetch a source's listing pages and report what its selectors matched.

    When a selector finds nothing, this does not just say so -- it reads the
    HTML that came back and proposes the selectors that would work, so a site
    redesign is a copy-paste fix rather than a debugging session."""
    from cadre.sources.base import suggest_body_selectors, suggest_list_selectors

    source = next((s for s in ALL_SOURCES if s.id == args.source), None)
    if source is None:
        print(f"unknown source: {args.source}", file=sys.stderr)
        return 2

    pattern = getattr(source, "article_pattern", None)
    problems, sample_article = 0, None

    with _fetcher(cfg) as fetcher:
        for url in source.listing_urls():
            print(f"\n  {url}")
            try:
                html = fetcher.get(url)
            except Exception as exc:
                print(f"    FETCH FAILED  {type(exc).__name__}: {exc}")
                problems += 1
                continue

            links = source.parse_listing(html, url)
            print(f"    {len(html):,} bytes · {len(links)} links parsed")

            for link in links[:5]:
                print(f"      [{link.published_at or '????-??-??'}] {link.title[:58]}")
            if links:
                sample_article = sample_article or links[0]
                continue

            problems += 1
            print("    NO LINKS -- selectors are stale.")
            if pattern is None:
                continue
            suggestions = suggest_list_selectors(html, url, pattern)
            if suggestions:
                print("    try these in _LIST_CONTAINERS "
                      f"(cadre/sources/{source.id}.py):")
                for selector, count in suggestions:
                    print(f"      {selector:<40} {count} article links")
            else:
                print("    no article-shaped links found at all -- check "
                      "_ARTICLE_HREF, or the page may be JavaScript-rendered.")

        # Body selectors break independently of listing selectors, so check one
        # real article too.
        if sample_article is not None:
            print(f"\n  article: {sample_article.url}")
            try:
                html = fetcher.get(sample_article.url)
                doc = source.parse_article(html, sample_article)
                cjk = sum(1 for ch in doc.text if "一" <= ch <= "鿿")
                print(f"    extracted {len(doc.text):,} chars ({cjk:,} CJK)")
                if cjk < 40:
                    problems += 1
                    print("    BODY TOO SHORT -- try these in _BODY_SELECTORS:")
                    for selector, score in suggest_body_selectors(html):
                        print(f"      {selector:<40} {score:,} CJK chars")
                else:
                    print(f"    {doc.text[:120]}...")
            except Exception as exc:
                problems += 1
                print(f"    FAILED  {type(exc).__name__}: {exc}")

    print(f"\n  {'OK' if not problems else str(problems) + ' problem(s)'}")
    return 0 if not problems else 1


def cmd_import(args, cfg: Config) -> int:
    """Import a roster (CPED, Wikidata, or any tabular file of officials).

    Always shows the resolved column mapping before importing, because a
    silently mis-mapped column is the failure mode that matters here."""
    conn = db.connect(cfg.db_path)
    db.migrate(conn)

    path = Path(args.file)
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 2

    overrides = {}
    for pair in args.map or []:
        if "=" not in pair:
            print(f"--map expects field=column, got {pair!r}", file=sys.stderr)
            return 2
        fname, column = pair.split("=", 1)
        overrides[fname.strip()] = column.strip()

    try:
        mapping, rows, columns = inspect_file(path, overrides, args.encoding)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"\n{path}  ({len(rows)} rows, {len(columns)} columns)\n")
    print("  mapped:")
    for fname in FIELDS_ORDER:
        if fname in mapping.resolved:
            print(f"    {fname:<16} <- {mapping.resolved[fname]}")
    if mapping.unmatched_fields:
        print("\n  not found:")
        for fname in mapping.unmatched_fields:
            hint = mapping.suggestions.get(fname)
            suffix = f"   (did you mean --map {fname}={hint!r} ?)" if hint else ""
            print(f"    {fname}{suffix}")
    if mapping.unused_columns:
        print(f"\n  unused columns: {', '.join(mapping.unused_columns[:12])}"
              + (" ..." if len(mapping.unused_columns) > 12 else ""))
    if not mapping.ok:
        print("\n  ABORT: no column matched name_zh. Use --map name_zh=<column>.",
              file=sys.stderr)
        return 1
    if not mapping.has_spells:
        print("\n  note: no position columns matched -- importing people only, "
              "no career spells.")

    try:
        report = import_roster(
            conn, path, overrides=overrides, dataset=args.dataset,
            max_tier=args.max_tier, dry_run=args.dry_run, encoding=args.encoding,
        )
    except ValueError as exc:
        print(f"\n  {exc}", file=sys.stderr)
        return 1

    print("\n  " + ("DRY RUN -- nothing written" if args.dry_run else "imported"))
    for line in report.lines():
        print(f"    {line}")
    for warning in report.warnings[:10]:
        print(f"    ! {warning}")
    if args.dry_run:
        print("\n  re-run without --dry-run to apply.")
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
    p.add_argument("--no-seed", action="store_true",
                   help="skip the smoke-test watchlist -- use this when you are "
                        "importing a real roster, since the seed rows carry no "
                        "birth year and would not dedup against it")
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

    p = sub.add_parser("import", help="import a roster file (CPED, Wikidata, CSV)")
    p.add_argument("file")
    p.add_argument("--dataset", default="cped",
                   help="name recorded as the provenance of these rows")
    p.add_argument("--map", action="append", metavar="FIELD=COLUMN",
                   help="override column matching, repeatable")
    p.add_argument("--max-tier", type=int, default=3,
                   help="watchlist people at this tier or more senior "
                        "(default 3); everyone is imported as a person regardless")
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--dry-run", action="store_true",
                   help="show the mapping and counts without writing")
    p.set_defaults(func=cmd_import)

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
