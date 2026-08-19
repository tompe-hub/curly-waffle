"""Significance scoring -- what floats to the top of the dashboard.

This replaces the alert tiering a push-based system would need. Nothing is
suppressed; everything is ordered. That removes the hardest calibration problem
in the design: there is no threshold to get wrong, only a ranking.
"""
from __future__ import annotations

import sqlite3

# A newly opened investigation is the highest-value signal in the system: it is
# the earliest formal confirmation, and everything after it is follow-through.
KIND_WEIGHT = {
    "investigation_opened": 1.00,
    "surrendered": 0.90,
    "detained": 0.85,
    "expelled": 0.80,
    "expelled_party": 0.75,
    "prosecuted": 0.60,
    "arrested": 0.60,
    "sentenced": 0.50,
    # 任免 vocabulary. The punitive verbs carry information on their own; 免去
    # is the routine word covering promotion, retirement and purge alike, so it
    # ranks mid-table and waits for the classifier.
    "recalled": 0.85,
    "dismissed": 0.85,
    "removed": 0.60,
    "resigned": 0.55,
    "appointed": 0.45,
}

# A departure published alongside an onward appointment is a reshuffle; a
# departure with nothing following it is the case worth looking at.
PAIRED_APPOINTMENT_DISCOUNT = 0.45

# Watchlist tier: 1 = Politburo and above, 2 = Central Committee full member,
# 3 = alternate / full-ministerial, 4 = vice-ministerial and below.
TIER_WEIGHT = {1: 1.00, 2: 0.85, 3: 0.70, 4: 0.55}

# Someone we have never seen before still matters -- coverage depth on officials
# nobody reports on is the entire point -- so an unknown person scores above a
# routine sentencing rather than being buried.
UNKNOWN_PERSON_WEIGHT = 0.45

# Name-attachment uncertainty is priced here and only here. Extraction
# confidence measures the phrase match; folding name doubt into it as well
# double-counted the same uncertainty.
GUESSED_NAME_PENALTY = 0.80
DOC_SUBJECT_PENALTY = 0.95


def significance(
    conn: sqlite3.Connection,
    *,
    kind: str,
    person_id: int | None,
    confidence: float,
    name_is_guess: bool,
    from_document: bool = False,
    paired_appointment: bool = False,
) -> float:
    kind_w = KIND_WEIGHT.get(kind, 0.4)

    if person_id is None:
        person_w = UNKNOWN_PERSON_WEIGHT
    else:
        row = conn.execute(
            "SELECT tier FROM watchlist WHERE person_id = ?", (person_id,)
        ).fetchone()
        person_w = TIER_WEIGHT.get(row["tier"], 0.5) if row else 0.5

    score = kind_w * person_w * confidence
    if name_is_guess:
        score *= GUESSED_NAME_PENALTY
    if from_document:
        score *= DOC_SUBJECT_PENALTY
    if paired_appointment:
        score *= PAIRED_APPOINTMENT_DISCOUNT
    return round(score, 4)
