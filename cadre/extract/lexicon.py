"""Curated phrase lexicon for discipline-inspection announcements.

Chinese personnel announcements are formulaic, and that formulaic core is worth
matching deterministically rather than handing to a model: it is cheap, it is
fast, and -- the part that actually matters -- it is auditable. Every signal the
system raises can be traced to a specific phrase in this file and a verbatim
span in an archived document.

The English gloss is fixed per phrase rather than machine-translated. The exact
wording is what drives the classification, so it must not drift.

Order matters: phrases are matched most-specific-first, and the first match on a
document wins for a given person.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Phrase:
    id: str
    zh: str
    kind: str
    confidence: float
    gloss: str


# kind vocabulary used downstream by scoring and the dashboard
KIND_LABELS = {
    "investigation_opened": "Under investigation",
    "surrendered": "Voluntarily surrendered",
    "detained": "Detained (留置)",
    "expelled": "Expelled from party and office (双开)",
    "expelled_party": "Expelled from the party",
    "prosecuted": "Transferred for prosecution",
    "arrested": "Arrested",
    "sentenced": "Sentenced",
}

PHRASES: list[Phrase] = [
    # -- investigation opened -------------------------------------------------
    Phrase(
        "ccdi.investigation.central",
        "接受中央纪委国家监委纪律审查和监察调查",
        "investigation_opened", 0.95,
        "undergoing disciplinary review and supervisory investigation by the "
        "Central Commission for Discipline Inspection and the National "
        "Supervisory Commission",
    ),
    Phrase(
        "ccdi.investigation.generic",
        "接受纪律审查和监察调查",
        "investigation_opened", 0.90,
        "undergoing disciplinary review and supervisory investigation",
    ),
    Phrase(
        "ccdi.investigation.filed",
        "立案审查调查",
        "investigation_opened", 0.90,
        "a case has been opened for review and investigation",
    ),
    Phrase(
        "ccdi.investigation.supervisory_only",
        "涉嫌严重职务违法",
        "investigation_opened", 0.75,
        "suspected of serious duty-related violations of law "
        "(non-party-member formulation)",
    ),
    Phrase(
        "ccdi.investigation.suspected",
        "涉嫌严重违纪违法",
        "investigation_opened", 0.75,
        "suspected of serious violations of discipline and law",
    ),
    # -- voluntary surrender: distinctive, and usually precedes the rest -------
    Phrase(
        "ccdi.surrender",
        "主动投案",
        "surrendered", 0.90,
        "voluntarily surrendered to the authorities",
    ),
    # -- detention ------------------------------------------------------------
    Phrase(
        "ccdi.detained",
        "留置",
        "detained", 0.70,
        "placed in liuzhi detention",
    ),
    # -- expulsion ------------------------------------------------------------
    Phrase(
        "ccdi.expelled.both",
        "开除党籍和公职",
        "expelled", 0.95,
        "expelled from the party and dismissed from public office",
    ),
    Phrase(
        "ccdi.expelled.both.alt",
        "开除党籍、开除公职",
        "expelled", 0.95,
        "expelled from the party and dismissed from public office",
    ),
    Phrase(
        "ccdi.expelled.shuangkai",
        "双开",
        "expelled", 0.90,
        "'double expulsion' -- from the party and from public office",
    ),
    Phrase(
        "ccdi.expelled.party",
        "开除党籍",
        "expelled_party", 0.85,
        "expelled from the Communist Party",
    ),
    # -- judicial handover ----------------------------------------------------
    Phrase(
        "ccdi.prosecuted.transfer",
        "移送检察机关依法审查起诉",
        "prosecuted", 0.92,
        "transferred to the procuratorate for review and prosecution",
    ),
    Phrase(
        "ccdi.prosecuted.transfer.short",
        "移送检察机关",
        "prosecuted", 0.85,
        "transferred to the procuratorate",
    ),
    Phrase(
        "ccdi.arrested",
        "依法决定逮捕",
        "arrested", 0.88,
        "placed under arrest by legal decision",
    ),
    Phrase(
        "ccdi.sentenced",
        "一审公开宣判",
        "sentenced", 0.85,
        "verdict delivered at first-instance public sentencing",
    ),
]

# Marks a position as explicitly former ("原"), which tells us the removal had
# already happened before this announcement.
FORMER_MARKERS = ("原", "时任")


# ---------------------------------------------------------------------------
# Appointment and removal (任免) language -- NPC Standing Committee decisions
# and State Council personnel notices.
#
# These read completely differently from discipline-inspection notices. The
# name is bracketed by the grammar (免去 X 的 Y 职务, 任命 X 为 Y) rather than
# sitting at the end of a title, so it can be captured directly instead of
# guessed. They also list many people per document, which regex handles
# naturally and the single-subject CCDI path does not.
#
# The distinction that matters most here is between the neutral and the
# punitive verbs. 免去 is the routine word and covers promotion, retirement and
# purge alike -- it needs the classifier to disambiguate. 撤销职务 and 罢免 are
# disciplinary, and carry much more information on their own.

@dataclass(frozen=True)
class PatternRule:
    id: str
    regex: str          # group 1 = name, group 2 = position
    kind: str
    confidence: float
    gloss: str


KIND_LABELS.update({
    "appointed": "Appointed",
    "removed": "Removed from post",
    "dismissed": "Dismissed from post (撤销职务)",
    "recalled": "Recalled (罢免)",
    "resigned": "Resigned",
})

_NAME = r"([一-鿿·]{2,5})"
_POS = r"(.{2,45}?)"

PATTERNS: list[PatternRule] = [
    # -- punitive: these are disciplinary acts, not routine reshuffling -------
    PatternRule(
        "npc.recalled", rf"罢免{_NAME}的{_POS}职务",
        "recalled", 0.92,
        "recalled from office by vote -- a disciplinary act, not a routine move",
    ),
    PatternRule(
        "npc.dismissed", rf"撤销{_NAME}的{_POS}职务",
        "dismissed", 0.90,
        "post revoked -- a disciplinary act, not a routine move",
    ),
    # -- neutral: ambiguous by design, needs classification -------------------
    PatternRule(
        "npc.resigned.accepted", rf"接受{_NAME}辞去{_POS}的请求",
        "resigned", 0.88,
        "resignation from the post accepted",
    ),
    PatternRule(
        "npc.resigned", rf"{_NAME}辞去{_POS}职务",
        "resigned", 0.80,
        "resigned from the post",
    ),
    PatternRule(
        "npc.removed", rf"免去{_NAME}的{_POS}职务",
        "removed", 0.90,
        "removed from the post -- the neutral formulation, which covers "
        "promotion, retirement and purge alike",
    ),
    PatternRule(
        "npc.appointed", rf"任命{_NAME}为{_POS}(?=[。；，、\n]|$)",
        "appointed", 0.90,
        "appointed to the post",
    ),
]

# A removal published alongside an onward appointment for the same person is a
# reshuffle. A removal with nothing following it is the interesting case.
NEUTRAL_DEPARTURE_KINDS = {"removed", "resigned"}
