"""Extraction is the layer that decides what the system claims, so these tests
are about what it must NOT do as much as what it must."""
from __future__ import annotations

from cadre.extract import extract_signals

KNOWN = {"唐仁健", "李晓鹏", "秦刚"}

INVESTIGATION = (
    "农业农村部党组书记、部长唐仁健涉嫌严重违纪违法，"
    "目前正接受中央纪委国家监委纪律审查和监察调查。"
)

EXPULSION = (
    "日前，经中共中央批准，中央纪委国家监委对中国光大集团股份公司原党委书记、"
    "董事长李晓鹏严重违纪违法问题进行了立案审查调查。"
    "依据有关规定，决定给予李晓鹏开除党籍处分；"
    "将其涉嫌犯罪问题移送检察机关依法审查起诉，所涉财物一并移送。"
)

UNKNOWN_PERSON = (
    "江南省人民政府原副省长张伟涉嫌严重违纪违法，目前正接受纪律审查和监察调查。"
)


def test_investigation_is_extracted_with_position():
    signals = extract_signals(INVESTIGATION, "", KNOWN)
    assert [s.kind for s in signals] == ["investigation_opened"]
    sig = signals[0]
    assert sig.raw_name == "唐仁健"
    assert not sig.name_is_guess
    assert "农业农村部" in sig.raw_position
    assert sig.confidence >= 0.9
    # the audit trail must contain the actual Chinese, verbatim
    assert "接受中央纪委国家监委纪律审查和监察调查" in sig.quoted_span


def test_expulsion_document_yields_the_full_progression():
    kinds = {s.kind for s in extract_signals(EXPULSION, "", KNOWN)}
    assert "expelled_party" in kinds
    assert "prosecuted" in kinds
    assert "investigation_opened" in kinds


def test_later_clauses_inherit_the_document_subject():
    """'将其涉嫌犯罪问题移送检察机关' names nobody -- the subject is carried
    from the document, not dropped."""
    signals = {s.kind: s for s in extract_signals(EXPULSION, "", KNOWN)}
    assert signals["prosecuted"].raw_name == "李晓鹏"
    assert signals["prosecuted"].from_document is True


def test_unknown_person_is_guessed_but_flagged_as_a_guess():
    signals = extract_signals(UNKNOWN_PERSON, "", KNOWN)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.raw_name == "张伟"
    assert sig.name_is_guess is True
    # confidence describes the phrase, not the name; name doubt is priced in scoring
    assert sig.confidence >= 0.9
    assert "副省长" in sig.raw_position


def test_position_marked_former_is_detected():
    signals = extract_signals(UNKNOWN_PERSON, "", KNOWN)
    assert signals[0].former is True   # 原副省长


def test_unrelated_text_produces_nothing():
    noise = "农业农村部部长唐仁健出席全国春耕生产工作会议并讲话，强调要抓好粮食生产。"
    assert extract_signals(noise, "", KNOWN) == []


def test_title_is_searched_as_well_as_body():
    title = "农业农村部党组书记、部长唐仁健涉嫌严重违纪违法接受中央纪委国家监委纪律审查和监察调查"
    signals = extract_signals("", title, KNOWN)
    assert signals and signals[0].raw_name == "唐仁健"
