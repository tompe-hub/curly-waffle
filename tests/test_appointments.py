"""任免 extraction: appointment and removal decisions.

Different grammar from discipline inspection -- the name is delimited by the
sentence structure, and one document names many people."""
from __future__ import annotations

from cadre.extract import extract_signals
from cadre.pipeline import run_daily
from cadre.sources import NpcSource

KNOWN = {"唐仁健", "李晓鹏", "秦刚"}

DECISION = (
    "第十四届全国人民代表大会常务委员会第十一次会议决定："
    "免去唐仁健的农业农村部部长职务。"
    "任命韩俊为农业农村部部长。"
    "免去王强的司法部副部长职务；任命王强为最高人民检察院副检察长。"
    "撤销赵国平的第十四届全国人民代表大会代表职务。"
    "接受孙立民辞去全国人民代表大会常务委员会委员的请求。"
)


def _by(signals, kind, name):
    return next(s for s in signals if s.kind == kind and s.raw_name == name)


def test_one_document_yields_every_person_named():
    signals = extract_signals(DECISION, "", KNOWN)
    pairs = {(s.kind, s.raw_name) for s in signals}
    assert ("removed", "唐仁健") in pairs
    assert ("appointed", "韩俊") in pairs
    assert ("removed", "王强") in pairs
    assert ("appointed", "王强") in pairs
    assert ("dismissed", "赵国平") in pairs
    assert ("resigned", "孙立民") in pairs


def test_captured_names_are_not_treated_as_guesses():
    """The grammar delimits the name, so it is read, not guessed -- even for
    someone we have never seen before. Whether they are in the database is a
    separate question that resolution answers."""
    signals = extract_signals(DECISION, "", KNOWN)
    assert _by(signals, "appointed", "韩俊").name_is_guess is False


def test_positions_are_captured_with_the_name():
    signals = extract_signals(DECISION, "", KNOWN)
    assert _by(signals, "removed", "唐仁健").raw_position == "农业农村部部长"
    assert _by(signals, "appointed", "韩俊").raw_position == "农业农村部部长"


def test_removal_with_an_onward_post_is_flagged_as_a_reshuffle():
    signals = extract_signals(DECISION, "", KNOWN)
    assert _by(signals, "removed", "王强").paired_appointment is True
    # 唐仁健 is removed with nothing following -- the interesting case
    assert _by(signals, "removed", "唐仁健").paired_appointment is False


def test_punitive_and_neutral_verbs_are_kept_distinct():
    """撤销职务 is a disciplinary act; 免去 is the routine word. Collapsing
    them would throw away the only signal 任免 text carries on its own."""
    signals = extract_signals(DECISION, "", KNOWN)
    assert _by(signals, "dismissed", "赵国平").kind == "dismissed"
    assert _by(signals, "removed", "唐仁健").kind == "removed"


def test_npc_source_runs_end_to_end(conn, cfg, fetcher):
    report = run_daily(conn, cfg, fetcher, sources=[NpcSource()])
    assert report.status == "ok"
    rows = conn.execute(
        """SELECT e.kind, e.significance, COALESCE(p.name_zh, e.raw_name) AS who
             FROM event e LEFT JOIN person p ON p.id = e.person_id"""
    ).fetchall()
    found = {(r["who"], r["kind"]): r["significance"] for r in rows}
    assert ("唐仁健", "removed") in found
    assert ("王强", "removed") in found
    # an unexplained departure must outrank a straight reshuffle
    assert found[("唐仁健", "removed")] > found[("王强", "removed")]
