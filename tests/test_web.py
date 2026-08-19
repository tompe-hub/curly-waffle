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
