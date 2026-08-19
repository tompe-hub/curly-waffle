"""Administrative rank, watchlist tier, and the sideline-post flag.

This is the domain content of the import. Three things get derived from a
roster row:

  rank_score   makes ranks comparable, so "promotion" can later be defined as
               an increase rather than hand-checked case by case.
  tier         drives significance ranking on the dashboard.
  is_sideline  marks the "kicked upstairs" destinations -- an NPC or CPPCC
               committee seat, a 巡视员 posting -- which read as lateral or
               even upward by rank and are career termination in fact. Without
               this flag a rank-delta classifier scores them as promotions.
"""
from __future__ import annotations

import re

# 行政级别. Both the formal (国家级正职) and colloquial (正国级) spellings appear
# in the wild, as do English renderings in translated datasets.
RANK_SCORES: dict[str, int] = {
    "正国级": 100, "国家级正职": 100, "national level": 100,
    "副国级": 90, "国家级副职": 90, "sub-national": 90, "vice-national": 90,
    "正部级": 80, "省部级正职": 80, "部级": 80,
    "provincial-ministerial": 80, "ministerial": 80,
    "副部级": 70, "省部级副职": 70, "vice-ministerial": 70, "vice-provincial": 70,
    "正厅级": 60, "厅局级正职": 60, "司局级正职": 60, "bureau": 60, "prefecture": 60,
    "副厅级": 50, "厅局级副职": 50, "司局级副职": 50, "vice-bureau": 50,
    "正处级": 40, "县处级正职": 40, "division": 40,
    "副处级": 30, "县处级副职": 30, "vice-division": 30,
    "正科级": 20, "乡科级正职": 20, "section": 20,
    "副科级": 10, "乡科级副职": 10, "vice-section": 10,
}

# Central Committee standing, which outranks bureaucratic level for our purposes.
_CC_TIER_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"政治局常委|常务委员会委员|standing committee of the political", re.I), 1),
    (re.compile(r"政治局委员|politburo", re.I), 1),
    (re.compile(r"书记处书记|secretariat", re.I), 1),
    (re.compile(r"候补(中央)?委员|alternate", re.I), 3),
    (re.compile(r"中央委员|central committee (full )?member|^full member", re.I), 2),
]

# Rank alone, when Central Committee standing is unknown.
_TIER_BY_SCORE = [(90, 1), (80, 3), (0, 4)]

SIDELINE_PATTERNS = [
    re.compile(r"人民代表大会常务委员会(副委员长|委员|副主任)"),
    re.compile(r"人大常委会(副委员长|委员|副主任)"),
    re.compile(r"政治协商会议.*(副主席|常务委员|委员)"),
    re.compile(r"政协.*(副主席|常务委员|委员)"),
    re.compile(r"巡视员|调研员|参事|顾问"),
    re.compile(r"(?i)\b(npc|cppcc) (standing committee|vice[- ]chair)"),
]

_NORMALISE = re.compile(r"[\s\-_·]+")


def _norm(text: str) -> str:
    return _NORMALISE.sub("", text).lower()


# Longest key first, or a substring match on a shorter key wins wrongly:
# 副部级 contains 部级, and "vice-ministerial" contains "ministerial", so both
# would score a rank tier too high.
_RANKS_BY_SPECIFICITY = sorted(
    ((_norm(k), v) for k, v in RANK_SCORES.items()),
    key=lambda kv: -len(kv[0]),
)


def rank_score(raw: str | None) -> int | None:
    """Map a rank string to a comparable score. None when unrecognised --
    which is information, not a zero."""
    if not raw:
        return None
    text = _norm(str(raw))
    for key, score in _RANKS_BY_SPECIFICITY:
        if key in text:
            return score
    return None


def is_sideline(position_title: str | None) -> bool:
    if not position_title:
        return False
    return any(p.search(position_title) for p in SIDELINE_PATTERNS)


def tier_for(
    *, cc_status: str | None = None, rank: str | None = None,
    position_title: str | None = None,
) -> int:
    """Watchlist tier: 1 = Politburo and above, 2 = Central Committee full
    member, 3 = alternate member or full-ministerial, 4 = everyone else.

    Committee standing and bureaucratic rank are two independent readings of
    seniority, and neither dominates the other. An NPC vice-chairman is 副国级
    and outranks an ordinary Central Committee member, while a Politburo member
    outranks their nominal rank. So take whichever reading is more senior
    rather than preferring one -- an earlier version checked committee standing
    first and filed 副国级 officials who also sat on the Central Committee as
    tier 2."""
    return min(_tier_from_committee(cc_status, position_title),
               _tier_from_rank(rank))


def _tier_from_committee(cc_status: str | None, position_title: str | None) -> int:
    haystack = " ".join(filter(None, (cc_status, position_title)))
    for pattern, tier in _CC_TIER_PATTERNS:
        if pattern.search(haystack):
            return tier
    return 4


def _tier_from_rank(rank: str | None) -> int:
    score = rank_score(rank)
    if score is None:
        return 4
    for threshold, tier in _TIER_BY_SCORE:
        if score >= threshold:
            return tier
    return 4
