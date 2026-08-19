"""End-to-end over the fixture corpus, plus the two properties the daily job
has to hold: idempotency and the empty-listing guard."""
from __future__ import annotations

from cadre.pipeline import reextract, run_daily
from cadre.sources import CcdiSource


def _run(conn, cfg, fetcher):
    return run_daily(conn, cfg, fetcher, sources=[CcdiSource()])


def test_full_run_produces_documents_signals_and_events(conn, cfg, fetcher):
    report = _run(conn, cfg, fetcher)
    assert report.status == "ok"

    docs = conn.execute("SELECT COUNT(*) FROM document").fetchone()[0]
    assert docs == 3          # two 中管干部 articles + one 省管干部

    events = conn.execute(
        """SELECT e.kind, p.name_zh, e.raw_name FROM event e
             LEFT JOIN person p ON p.id = e.person_id"""
    ).fetchall()
    by_name = {(r["name_zh"] or r["raw_name"]): r["kind"] for r in events}
    assert "唐仁健" in by_name
    assert "李晓鹏" in by_name
    assert "张伟" in by_name   # unresolved, still surfaced


def test_unresolved_signals_land_in_the_review_queue(conn, cfg, fetcher):
    _run(conn, cfg, fetcher)
    row = conn.execute(
        "SELECT * FROM signal WHERE raw_name = '张伟'"
    ).fetchone()
    assert row["resolution"] == "unknown_person"
    assert row["person_id"] is None


def test_run_is_idempotent(conn, cfg, fetcher):
    _run(conn, cfg, fetcher)
    counts = lambda: (
        conn.execute("SELECT COUNT(*) FROM document").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM signal").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM event").fetchone()[0],
    )
    first = counts()
    _run(conn, cfg, fetcher)
    assert counts() == first


def test_every_signal_points_at_an_archived_document(conn, cfg, fetcher):
    """The archive is the source of truth; a claim we cannot show the source
    for is worse than no claim."""
    _run(conn, cfg, fetcher)
    rows = conn.execute(
        """SELECT d.archive_path FROM signal s JOIN document d ON d.id = s.document_id"""
    ).fetchall()
    assert rows
    for row in rows:
        assert (cfg.archive_dir / row["archive_path"]).exists()


def test_empty_listing_is_flagged_not_treated_as_quiet(conn, cfg, fetcher, monkeypatch):
    """A source that has produced links before and now produces none has
    probably been redesigned. Reporting 'nothing happened' would be a lie."""
    _run(conn, cfg, fetcher)

    source = CcdiSource()
    monkeypatch.setattr(source, "parse_listing", lambda html, base_url: [])
    report = run_daily(conn, cfg, fetcher, sources=[source])

    assert report.sources[0].status == "empty"
    assert "selectors" in report.sources[0].error


def test_reextract_replays_the_archive_without_duplicating(conn, cfg, fetcher):
    _run(conn, cfg, fetcher)
    before = conn.execute("SELECT COUNT(*) FROM signal").fetchone()[0]
    reextract(conn, cfg)
    assert conn.execute("SELECT COUNT(*) FROM signal").fetchone()[0] == before


def test_clustering_collapses_repeats_into_one_event(conn, cfg, fetcher):
    _run(conn, cfg, fetcher)
    rows = conn.execute(
        """SELECT e.id, COUNT(s.id) AS n FROM event e
             JOIN signal s ON s.event_id = e.id
            GROUP BY e.id"""
    ).fetchall()
    assert rows
    # every signal is attached to exactly one event
    total_signals = conn.execute("SELECT COUNT(*) FROM signal").fetchone()[0]
    assert sum(r["n"] for r in rows) == total_signals


def test_listing_parser_ignores_navigation_links(conn, cfg, fetcher):
    source = CcdiSource()
    html = fetcher.get("https://www.ccdi.gov.cn/scdcn/zggb/")
    links = source.parse_listing(html, "https://www.ccdi.gov.cn/scdcn/zggb/")
    assert len(links) == 2
    assert all(l.url.endswith(".shtml") for l in links)
    assert links[0].published_at == "2024-05-18"
