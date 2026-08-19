"""Static snapshot of the dashboard.

A single self-contained HTML file with no server behind it, for reading on a
phone, mailing to someone, or archiving what the dashboard said on a given day.
The review controls are omitted because they cannot work without the app.

`--sample` marks the output as fixture-derived. That matters more than it
sounds: the test corpus contains invented officials written in the exact format
of real discipline-inspection notices, and an unlabelled snapshot of it would
read as genuine reporting that named people are under investigation.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cadre.extract.lexicon import KIND_LABELS, PATTERNS, PHRASES

TEMPLATE_DIR = Path(__file__).parent / "templates"
GLOSS_BY_RULE = {r.id: r.gloss for r in (*PHRASES, *PATTERNS)}


def load_synthetic_names(path: Path) -> set[str]:
    """Names known to be invented, from a manifest kept beside the fixtures."""
    if not path.exists():
        return set()
    return {
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def render(
    conn: sqlite3.Connection,
    *,
    sample: bool = False,
    synthetic_names: set[str] | None = None,
    limit: int = 200,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    events = conn.execute(
        """
        SELECT e.*, p.name_zh, p.name_pinyin, w.tier
          FROM event e
          LEFT JOIN person p ON p.id = e.person_id
          LEFT JOIN watchlist w ON w.person_id = e.person_id
         ORDER BY e.significance DESC, e.last_seen_at DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()

    invented = synthetic_names or set()
    rows = []
    for event in events:
        item = dict(event)
        name = event["name_zh"] or event["raw_name"]
        item["synthetic"] = bool(sample and name and name in invented)
        rows.append(item)

    evidence = {
        event["id"]: conn.execute(
            """SELECT s.quoted_span, s.rule_id, s.confidence, s.raw_position,
                      d.source_id
                 FROM signal s JOIN document d ON d.id = s.document_id
                WHERE s.event_id = ? ORDER BY s.confidence DESC LIMIT 3""",
            (event["id"],),
        ).fetchall()
        for event in events
    }

    counts = {
        "people": conn.execute("SELECT COUNT(*) FROM person").fetchone()[0],
        "documents": conn.execute("SELECT COUNT(*) FROM document").fetchone()[0],
    }

    return env.get_template("export.html").render(
        events=rows, evidence=evidence, counts=counts,
        labels=KIND_LABELS, glosses=GLOSS_BY_RULE, sample=sample,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
