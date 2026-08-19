"""Signal -> event clustering.

One real-world happening reaches us several times: the CCDI notice, a provincial
mirror of it, a roster page losing the person, a wire report. Without clustering
the dashboard shows six rows for one purge.

Clustering rule for v0: same person, same kind, within a 90-day window. Distinct
kinds stay distinct events on purpose -- investigation, expulsion and
prosecution are separate milestones in the same career arc, and collapsing them
would hide the progression that makes the arc readable.
"""
from __future__ import annotations

import sqlite3

CLUSTER_WINDOW_DAYS = 90


def attach(
    conn: sqlite3.Connection,
    *,
    person_id: int | None,
    raw_name: str | None,
    kind: str,
    event_date: str | None,
    summary: str,
    significance: float,
) -> int:
    """Find or create the event this signal belongs to, and return its id."""
    if person_id is not None:
        row = conn.execute(
            """
            SELECT id, significance FROM event
             WHERE person_id = ? AND kind = ?
               AND julianday(COALESCE(?, date('now')))
                   - julianday(COALESCE(event_date, first_seen_at)) BETWEEN -? AND ?
             ORDER BY first_seen_at DESC LIMIT 1
            """,
            (person_id, kind, event_date, CLUSTER_WINDOW_DAYS, CLUSTER_WINDOW_DAYS),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id, significance FROM event
             WHERE person_id IS NULL AND raw_name = ? AND kind = ?
             ORDER BY first_seen_at DESC LIMIT 1
            """,
            (raw_name, kind),
        ).fetchone()

    if row is not None:
        # Corroboration: refresh recency and keep the strongest significance
        # seen, but do not reset review state -- a seen event stays seen.
        conn.execute(
            """
            UPDATE event
               SET last_seen_at = datetime('now'),
                   significance = MAX(significance, ?),
                   event_date = COALESCE(event_date, ?)
             WHERE id = ?
            """,
            (significance, event_date, row["id"]),
        )
        return int(row["id"])

    cur = conn.execute(
        """
        INSERT INTO event
            (person_id, raw_name, kind, event_date, first_seen_at, last_seen_at,
             significance, review_state, summary)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), ?, 'new', ?)
        """,
        (person_id, raw_name, kind, event_date, significance, summary),
    )
    return int(cur.lastrowid)
