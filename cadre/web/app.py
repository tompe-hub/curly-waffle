"""The dashboard.

Its job is to answer "what changed since I last looked" in about a minute, so
the two things it has to get right are the since-you-last-looked boundary and
the ranking. Everything is surfaced; nothing is suppressed. There is no
threshold to tune -- only an order.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from cadre import db
from cadre.config import Config
from cadre.extract.lexicon import KIND_LABELS, PHRASES

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
GLOSS_BY_RULE = {p.id: p.gloss for p in PHRASES}

# Refreshing the page should not move the "since you last looked" line out from
# under you, so a new visit is only recorded after a real gap.
VISIT_GAP_HOURS = 4

app = FastAPI(title="cadre-watch")


def _conn():
    cfg = Config.load()
    conn = db.connect(cfg.db_path)
    db.migrate(conn)
    return conn


def _boundary(conn) -> str | None:
    row = conn.execute("SELECT at FROM visit ORDER BY at DESC LIMIT 1").fetchone()
    boundary = row["at"] if row else None
    stale = conn.execute(
        "SELECT 1 FROM visit WHERE at > datetime('now', ?) LIMIT 1",
        (f"-{VISIT_GAP_HOURS} hours",),
    ).fetchone()
    if not stale:
        conn.execute("INSERT INTO visit (at) VALUES (datetime('now'))")
        conn.commit()
    return boundary


@app.get("/", response_class=HTMLResponse)
def whats_new(request: Request, show: str = "new"):
    conn = _conn()
    boundary = _boundary(conn)

    where, params = [], []
    if show == "new":
        where.append("e.review_state = 'new'")
    elif show == "since" and boundary:
        where.append("e.last_seen_at > ?")
        params.append(boundary)
    elif show == "open":
        where.append("e.review_state IN ('new', 'watching')")
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    events = conn.execute(
        f"""
        SELECT e.*, p.name_zh, p.name_pinyin, w.tier,
               (SELECT COUNT(*) FROM signal s WHERE s.event_id = e.id) AS n_signals
          FROM event e
          LEFT JOIN person p ON p.id = e.person_id
          LEFT JOIN watchlist w ON w.person_id = e.person_id
          {clause}
         ORDER BY e.significance DESC, e.last_seen_at DESC
         LIMIT 200
        """,
        params,
    ).fetchall()

    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "request": request, "events": events, "boundary": boundary, "show": show,
            "labels": KIND_LABELS, "glosses": GLOSS_BY_RULE, "counts": _counts(conn),
            "evidence": {e["id"]: _evidence(conn, e["id"]) for e in events},
        },
    )


@app.get("/person/{person_id}", response_class=HTMLResponse)
def person(request: Request, person_id: int):
    conn = _conn()
    row = conn.execute(
        """SELECT p.*, w.tier FROM person p
           LEFT JOIN watchlist w ON w.person_id = p.id WHERE p.id = ?""",
        (person_id,),
    ).fetchone()
    if row is None:
        return HTMLResponse("<h1>404</h1>", status_code=404)

    events = conn.execute(
        "SELECT * FROM event WHERE person_id = ? ORDER BY COALESCE(event_date, first_seen_at) DESC",
        (person_id,),
    ).fetchall()
    spells = conn.execute(
        """SELECT s.*, pos.title_zh, o.name_zh AS org_name
             FROM spell s JOIN position pos ON pos.id = s.position_id
             LEFT JOIN org o ON o.id = pos.org_id
            WHERE s.person_id = ? ORDER BY COALESCE(s.start_date,'') DESC""",
        (person_id,),
    ).fetchall()
    signals = conn.execute(
        """SELECT s.*, d.url, d.title AS doc_title, d.published_at, d.source_id
             FROM signal s JOIN document d ON d.id = s.document_id
            WHERE s.person_id = ? ORDER BY d.published_at DESC""",
        (person_id,),
    ).fetchall()

    return TEMPLATES.TemplateResponse(
        request,
        "person.html",
        {"request": request, "person": row, "events": events, "spells": spells,
         "signals": signals, "labels": KIND_LABELS, "glosses": GLOSS_BY_RULE,
         "counts": _counts(conn)},
    )


@app.get("/review", response_class=HTMLResponse)
def review(request: Request):
    """Signals whose name could not be pinned to exactly one person."""
    conn = _conn()
    rows = conn.execute(
        """
        SELECT s.*, d.url, d.title AS doc_title, d.published_at, d.source_id
          FROM signal s JOIN document d ON d.id = s.document_id
         WHERE s.resolution != 'resolved'
         ORDER BY s.confidence DESC, s.created_at DESC
         LIMIT 200
        """
    ).fetchall()
    candidates = {
        r["id"]: conn.execute(
            """SELECT rc.*, p.name_zh, p.notes FROM resolution_candidate rc
                 JOIN person p ON p.id = rc.person_id
                WHERE rc.signal_id = ? ORDER BY rc.score DESC""",
            (r["id"],),
        ).fetchall()
        for r in rows
    }
    return TEMPLATES.TemplateResponse(
        request,
        "review.html",
        {"request": request, "signals": rows, "candidates": candidates,
         "labels": KIND_LABELS, "glosses": GLOSS_BY_RULE, "counts": _counts(conn)},
    )


@app.get("/runs", response_class=HTMLResponse)
def runs(request: Request):
    conn = _conn()
    rows = conn.execute("SELECT * FROM run ORDER BY id DESC LIMIT 30").fetchall()
    per_source = {
        r["id"]: conn.execute(
            "SELECT * FROM run_source WHERE run_id = ? ORDER BY source_id", (r["id"],)
        ).fetchall()
        for r in rows
    }
    return TEMPLATES.TemplateResponse(
        request,
        "runs.html",
        {"request": request, "runs": rows, "per_source": per_source, "counts": _counts(conn)},
    )


@app.post("/event/{event_id}/state")
def set_state(event_id: int, state: str = Form(...), back: str = Form("/")):
    conn = _conn()
    if state in ("new", "seen", "confirmed", "dismissed", "watching"):
        conn.execute(
            "UPDATE event SET review_state = ?, reviewed_at = ? WHERE id = ?",
            (state, datetime.now(timezone.utc).isoformat(timespec="seconds"), event_id),
        )
        conn.commit()
    return RedirectResponse(back, status_code=303)


@app.post("/review/{signal_id}/assign")
def assign(signal_id: int, person_id: int = Form(...)):
    """Attach an ambiguous signal to the person a human picked."""
    conn = _conn()
    sig = conn.execute("SELECT * FROM signal WHERE id = ?", (signal_id,)).fetchone()
    if sig is not None:
        conn.execute(
            "UPDATE signal SET person_id = ?, resolution = 'resolved' WHERE id = ?",
            (person_id, signal_id),
        )
        if sig["event_id"]:
            conn.execute(
                "UPDATE event SET person_id = ?, raw_name = NULL WHERE id = ?",
                (person_id, sig["event_id"]),
            )
        conn.commit()
    return RedirectResponse("/review", status_code=303)


@app.post("/review/{signal_id}/create-person")
def create_person(signal_id: int, tier: int = Form(4)):
    """Promote an unknown name into a real person record, and watch them."""
    conn = _conn()
    sig = conn.execute("SELECT * FROM signal WHERE id = ?", (signal_id,)).fetchone()
    if sig is not None and sig["raw_name"]:
        cur = conn.execute(
            "INSERT INTO person (name_zh, notes) VALUES (?, ?)",
            (sig["raw_name"], f"created from signal {signal_id}: {sig['raw_position'] or ''}"),
        )
        person_id = int(cur.lastrowid)
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (person_id, tier) VALUES (?, ?)",
            (person_id, tier),
        )
        conn.execute(
            "UPDATE signal SET person_id = ?, resolution = 'resolved' WHERE id = ?",
            (person_id, signal_id),
        )
        if sig["event_id"]:
            conn.execute(
                "UPDATE event SET person_id = ?, raw_name = NULL WHERE id = ?",
                (person_id, sig["event_id"]),
            )
        conn.commit()
    return RedirectResponse("/review", status_code=303)


def _counts(conn) -> dict:
    one = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "new_events": one("SELECT COUNT(*) FROM event WHERE review_state = 'new'"),
        "review": one("SELECT COUNT(*) FROM signal WHERE resolution != 'resolved'"),
        "people": one("SELECT COUNT(*) FROM person"),
        "documents": one("SELECT COUNT(*) FROM document"),
    }


def _evidence(conn, event_id: int):
    return conn.execute(
        """SELECT s.quoted_span, s.rule_id, s.confidence, s.raw_position,
                  d.url, d.source_id, d.published_at
             FROM signal s JOIN document d ON d.id = s.document_id
            WHERE s.event_id = ? ORDER BY s.confidence DESC LIMIT 3""",
        (event_id,),
    ).fetchall()
