from __future__ import annotations

from cadre.score import significance


def _pid(conn, name):
    return conn.execute("SELECT id FROM person WHERE name_zh = ?", (name,)).fetchone()["id"]


def test_seniority_outranks_juniority_for_the_same_signal(conn):
    senior = significance(conn, kind="investigation_opened", person_id=_pid(conn, "秦刚"),
                          confidence=0.95, name_is_guess=False)
    junior = significance(conn, kind="investigation_opened", person_id=_pid(conn, "李晓鹏"),
                          confidence=0.95, name_is_guess=False)
    assert senior > junior


def test_new_investigation_outranks_follow_through(conn):
    pid = _pid(conn, "唐仁健")
    opened = significance(conn, kind="investigation_opened", person_id=pid,
                          confidence=0.95, name_is_guess=False)
    sentenced = significance(conn, kind="sentenced", person_id=pid,
                             confidence=0.95, name_is_guess=False)
    assert opened > sentenced


def test_unknown_person_still_surfaces(conn):
    """Coverage of officials nobody reports on is the point, so a fresh
    investigation into an unidentified official must outrank routine
    follow-through on someone already known."""
    unknown = significance(conn, kind="investigation_opened", person_id=None,
                           confidence=0.9, name_is_guess=True)
    known_followup = significance(conn, kind="prosecuted", person_id=_pid(conn, "李晓鹏"),
                                  confidence=0.92, name_is_guess=False,
                                  from_document=True)
    assert unknown > known_followup


def test_guessed_names_are_discounted(conn):
    pid = _pid(conn, "唐仁健")
    kw = dict(kind="investigation_opened", person_id=pid, confidence=0.9)
    assert significance(conn, name_is_guess=True, **kw) < significance(conn, name_is_guess=False, **kw)
