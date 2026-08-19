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
