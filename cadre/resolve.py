"""Entity resolution: a name string on a page -> a person in the database.

Chinese names are short and homonyms are common enough that "exact string match
is unique" cannot be assumed at scale. So resolution has three outcomes, and
only one of them proceeds automatically:

    resolved       exactly one person carries this name  -> attach
    ambiguous      several do                            -> review queue
    unknown_person nobody does                           -> review queue

Anything the system is not sure about becomes a human decision rather than a
silent guess. On a dashboard that costs a glance; a wrong attachment costs
trust.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class Resolution:
    status: str                       # resolved | ambiguous | unknown_person
    person_id: int | None = None
    candidates: list[tuple[int, float, str]] = field(default_factory=list)


def resolve_name(
    conn: sqlite3.Connection, raw_name: str, raw_position: str | None
) -> Resolution:
    rows = conn.execute(
        "SELECT id, name_zh FROM person WHERE name_zh = ?", (raw_name,)
    ).fetchall()

    if not rows:
        return Resolution(status="unknown_person")
    if len(rows) == 1:
        return Resolution(status="resolved", person_id=rows[0]["id"])

    # Several people share the name. Score each by how much their most recent
    # known position overlaps the position string in the announcement -- that is
    # the discriminator a human would use first.
    candidates = []
    for row in rows:
        score = _position_overlap(conn, row["id"], raw_position)
        candidates.append((row["id"], score, "name_exact+position_overlap"))
    candidates.sort(key=lambda c: -c[1])
    return Resolution(status="ambiguous", candidates=candidates)


def _position_overlap(
    conn: sqlite3.Connection, person_id: int, raw_position: str | None
) -> float:
    if not raw_position:
        return 0.0
    rows = conn.execute(
        """
        SELECT p.title_zh, o.name_zh AS org_name
          FROM spell s
          JOIN position p ON p.id = s.position_id
          LEFT JOIN org o ON o.id = p.org_id
         WHERE s.person_id = ?
         ORDER BY COALESCE(s.start_date, '') DESC
         LIMIT 5
        """,
        (person_id,),
    ).fetchall()
    if not rows:
        return 0.0
    best = 0.0
    for row in rows:
        for value in (row["title_zh"], row["org_name"]):
            if not value:
                continue
            shared = len(set(value) & set(raw_position))
            best = max(best, shared / max(len(set(value)), 1))
    return round(best, 3)


def known_names(conn: sqlite3.Connection) -> set[str]:
    """Every name the extractor should try to match by containment.

    Deliberately all of `person`, not just the watchlist: recognising a name we
    already know about is useful even when that person is not being actively
    watched."""
    return {r["name_zh"] for r in conn.execute("SELECT name_zh FROM person")}
