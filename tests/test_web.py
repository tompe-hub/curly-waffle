"""Dashboard smoke tests: every view renders, and the review actions actually
change state."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cadre.pipeline import run_daily
from cadre.sources import CcdiSource


@pytest.fixture
def client(conn, cfg, fetcher, monkeypatch):
    run_daily(conn, cfg, fetcher, sources=[CcdiSource()])
    monkeypatch.setenv("CADRE_DATA", str(cfg.data_dir))
    monkeypatch.setenv("CADRE_DB", str(cfg.db_path))
    monkeypatch.setenv("CADRE_ARCHIVE", str(cfg.archive_dir))
    from cadre.web.app import app
    return TestClient(app)


def test_whats_new_lists_events_with_their_evidence(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "唐仁健" in r.text
    # the verbatim Chinese and its fixed English gloss must both be shown
    assert "接受中央纪委国家监委纪律审查和监察调查" in r.text
    assert "disciplinary review and supervisory investigation" in r.text


def test_review_queue_shows_unresolved_names(client):
    r = client.get("/review")
    assert r.status_code == 200
    assert "张伟" in r.text
    assert "unknown_person" in r.text


def test_runs_view_renders(client):
    assert client.get("/runs").status_code == 200


def test_person_page_renders(client, conn):
    pid = conn.execute("SELECT id FROM person WHERE name_zh = '唐仁健'").fetchone()["id"]
    r = client.get(f"/person/{pid}")
    assert r.status_code == 200
    assert "唐仁健" in r.text


def test_marking_an_event_changes_its_state(client, conn):
    event_id = conn.execute("SELECT id FROM event LIMIT 1").fetchone()["id"]
    r = client.post(f"/event/{event_id}/state",
                    data={"state": "confirmed", "back": "/"}, follow_redirects=False)
    assert r.status_code == 303
    state = conn.execute("SELECT review_state FROM event WHERE id = ?", (event_id,)).fetchone()
    assert state["review_state"] == "confirmed"


def test_creating_a_person_from_the_queue_resolves_the_signal(client, conn):
    sig = conn.execute("SELECT * FROM signal WHERE raw_name = '张伟'").fetchone()
    r = client.post(f"/review/{sig['id']}/create-person",
                    data={"tier": "4"}, follow_redirects=False)
    assert r.status_code == 303

    after = conn.execute("SELECT * FROM signal WHERE id = ?", (sig["id"],)).fetchone()
    assert after["resolution"] == "resolved"
    assert after["person_id"] is not None
    event = conn.execute("SELECT * FROM event WHERE id = ?", (sig["event_id"],)).fetchone()
    assert event["person_id"] == after["person_id"]


def test_appointment_rows_show_their_english_gloss(client, conn, cfg, fetcher):
    """Every rule id in either lexicon must resolve to a fixed gloss. Building
    the lookup from one lexicon left the 任免 sources rendering a bare rule id
    where the explanation belongs."""
    from cadre.extract.lexicon import PATTERNS, PHRASES
    from cadre.web.app import GLOSS_BY_RULE

    for rule in (*PHRASES, *PATTERNS):
        assert GLOSS_BY_RULE.get(rule.id), f"no gloss for {rule.id}"

    from cadre.pipeline import run_daily
    from cadre.sources import NpcSource
    run_daily(conn, cfg, fetcher, sources=[NpcSource()])
    body = client.get("/?show=new").text
    assert "removed from the post" in body
    assert "npc.removed</code>" in body                    # provenance, fine
    assert '<div class="gloss">npc.removed' not in body    # but never as the gloss


# ----------------------------------------------------------------- export ---

def test_export_is_self_contained_and_has_no_controls(conn, cfg, fetcher):
    """A snapshot has no server behind it, so the review controls must not
    appear -- and nothing may reference a stylesheet that will not be there."""
    from cadre.pipeline import run_daily
    from cadre.sources import CcdiSource
    from cadre.web.export import render

    run_daily(conn, cfg, fetcher, sources=[CcdiSource()])
    html = render(conn)
    assert "唐仁健" in html
    assert "<form" not in html
    assert "<link" not in html          # styles are inline
    assert "src=" not in html


def test_sample_export_labels_invented_people(conn, cfg, fetcher):
    """The fixtures contain invented officials written in the format of real
    announcements. An unlabelled snapshot of them would read as reporting."""
    from pathlib import Path

    from cadre.pipeline import run_daily
    from cadre.sources import CcdiSource
    from cadre.web.export import load_synthetic_names, render

    run_daily(conn, cfg, fetcher, sources=[CcdiSource()])
    names = load_synthetic_names(
        Path(__file__).parent / "fixtures" / "SYNTHETIC_NAMES.txt")
    assert "张伟" in names
    assert "唐仁健" not in names        # a real, documented case

    html = render(conn, sample=True, synthetic_names=names)
    assert "SAMPLE DATA" in html
    assert "SYNTHETIC" in html

    plain = render(conn, sample=False)
    assert "SAMPLE DATA" not in plain
    assert "SYNTHETIC" not in plain


def test_export_escapes_document_text(conn, cfg, fetcher):
    """Quoted spans come from fetched pages -- they are untrusted input and
    must not be able to inject markup into a file that gets shared."""
    from cadre.web.export import render

    conn.execute(
        """INSERT INTO document (sha256, source_id, url, title, fetched_at, archive_path)
           VALUES ('x', 'ccdi', 'https://x.invalid/a', 't', datetime('now'), 'a')"""
    )
    doc_id = conn.execute("SELECT id FROM document").fetchone()["id"]
    conn.execute(
        """INSERT INTO event (kind, first_seen_at, last_seen_at, significance, raw_name)
           VALUES ('investigation_opened', datetime('now'), datetime('now'), 1.0, 'x')"""
    )
    event_id = conn.execute("SELECT id FROM event").fetchone()["id"]
    conn.execute(
        """INSERT INTO signal (document_id, event_id, kind, raw_name, quoted_span,
                               rule_id, confidence, resolution)
           VALUES (?, ?, 'investigation_opened', 'x',
                   '<script>alert(1)</script>', 'r', 0.9, 'unknown_person')""",
        (doc_id, event_id),
    )
    conn.commit()
    html = render(conn)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
