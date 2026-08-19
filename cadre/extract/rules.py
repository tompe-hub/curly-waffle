"""Rule-based signal extraction.

Two ways to attach a name to a matched phrase:

  1. Watchlist containment. We hold a bounded set of names (~400), so scanning
     the document for known names and taking the one nearest before the trigger
     phrase is both cheap and reliable. This is the high-confidence path.

  2. Surname-anchored guessing, for people not yet in the database. CCDI
     headlines put the name immediately before the trigger phrase, after the
     job title, so reading backwards from the trigger and testing against a
     surname list recovers most of them. These are LOW confidence by
     construction and are never auto-resolved -- they land in the review queue
     so a human can decide whether to add the person.

The failure mode we care about is a wrong name attached to a real purge, which
is worse than no name at all. Hence: guesses are always flagged as guesses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from cadre.extract.lexicon import (
    FORMER_MARKERS,
    NEUTRAL_DEPARTURE_KINDS,
    PATTERNS,
    PHRASES,
)

EXTRACTOR_VERSION = "rules-2"

# Bump the leading number whenever a change would alter output for an already
# extracted document; the pipeline re-extracts the archive when it changes.

_SEGMENT_SPLIT = re.compile(r"[。！？；\n]+")
_MAX_SPAN = 220
# Markers that sit immediately after the subject of the clause. The name is
# read backwards from the EARLIEST of these, not from the matched phrase --
# the phrase can appear much later in the same sentence.
_SUBJECT_MARKERS = (
    "涉嫌", "严重违纪违法", "主动投案", "接受纪律审查", "接受中央纪委",
    "被开除", "被查", "严重违法",
)

# Top Chinese surnames; covers the large majority of cadre names.
_SURNAMES_2 = {
    "欧阳", "司马", "上官", "诸葛", "东方", "夏侯", "皇甫", "尉迟", "公孙", "慕容",
    "长孙", "宇文", "司徒", "鲜于", "端木",
}
_SURNAMES_1 = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘"
    "于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江"
    "尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤耿聂章鲁岳翟殷詹申欧"
)

# Characters that commonly end a job title and therefore mark the boundary just
# before a name.
_TITLE_TAIL = set("长记员席任理事官书主委总监局部厅处科司院校组")


@dataclass(frozen=True)
class RawSignal:
    kind: str
    raw_name: str
    raw_position: str | None
    quoted_span: str
    rule_id: str
    confidence: float          # certainty of the PHRASE match, nothing else
    name_is_guess: bool        # name was surname-guessed, not matched
    from_document: bool        # subject inherited from the document, not this clause
    former: bool
    paired_appointment: bool = False   # a removal published with an onward post


def extract_signals(text: str, title: str, known_names: set[str]) -> list[RawSignal]:
    """Return one signal per (kind, name) found in the document.

    `title` is prepended because CCDI headlines carry the person, the position
    and the action in a single well-formed clause -- often more cleanly than the
    body does."""
    haystack = f"{title}。{text}" if title else text
    found: dict[tuple[str, str], RawSignal] = {}

    # These announcements are almost always about one person, and the name is
    # stated once up front. Later clauses say "其" ("his/her"), so a clause-local
    # lookup finds nothing. Carrying a document-level subject recovers the
    # follow-through signals -- expulsion, prosecution -- that would otherwise
    # be dropped for having no name attached.
    doc_subject = _document_subject(haystack, known_names)

    for segment in _segments(haystack):
        for phrase in PHRASES:
            idx = segment.find(phrase.zh)
            if idx < 0:
                continue

            name, is_guess = _subject_for(segment, idx, known_names)
            from_document = False
            if not name and doc_subject:
                name, is_guess, from_document = doc_subject, False, True
            if not name:
                continue

            position = _position_before(segment, name)
            # Name uncertainty is deliberately NOT folded in here. Mixing
            # "is this phrase a real signal" with "is this the right person"
            # into one number meant the two discounts compounded, and a fresh
            # investigation into an unidentified official ended up ranked below
            # routine follow-up on a known one -- the opposite of what a
            # coverage-first tool should do.
            signal = RawSignal(
                kind=phrase.kind,
                raw_name=name,
                raw_position=position,
                quoted_span=segment[:_MAX_SPAN],
                rule_id=phrase.id,
                confidence=phrase.confidence,
                name_is_guess=is_guess,
                from_document=from_document,
                former=any(m in (position or "") for m in FORMER_MARKERS),
            )
            key = (signal.kind, signal.raw_name)
            best = found.get(key)
            if best is None or signal.confidence > best.confidence:
                found[key] = signal
            break  # first (most specific) phrase wins for this segment

    for signal in _pattern_signals(haystack, known_names):
        key = (signal.kind, signal.raw_name)
        best = found.get(key)
        if best is None or signal.confidence > best.confidence:
            found[key] = signal

    return sorted(_mark_paired(found.values()), key=lambda s: -s.confidence)


def _pattern_signals(haystack: str, known_names: set[str]) -> list[RawSignal]:
    """Appointment/removal extraction.

    Unlike the discipline-inspection path, the name here is delimited by the
    grammar itself, so it is captured rather than guessed -- and one document
    routinely names dozens of people, which finditer handles and a
    single-subject scan does not."""
    out: list[RawSignal] = []
    for rule in PATTERNS:
        for match in re.finditer(rule.regex, haystack):
            name = match.group(1).strip("·、，,的 ")
            position = match.group(2).strip("·、，,的 ")
            if not position:
                continue
            known = name in known_names
            if not known and not _plausible_name(name):
                continue
            out.append(RawSignal(
                kind=rule.kind,
                raw_name=name,
                raw_position=position,
                quoted_span=_span_around(haystack, match.start(), match.end()),
                rule_id=rule.id,
                confidence=rule.confidence,
                # The grammar delimits the name, so this is not a guess even
                # when we have never seen the person before. Whether they are
                # in the database is a separate question, answered by
                # resolution rather than by extraction.
                name_is_guess=False,
                from_document=False,
                former=any(m in position for m in FORMER_MARKERS),
            ))
    return out


def _mark_paired(signals) -> list[RawSignal]:
    """Flag removals that came with an onward appointment in the same document.

    A removal published alongside a new post is routine reshuffling; a removal
    with nothing following it is the case worth looking at. This is the single
    most useful discriminator available in 任免 text without a classifier."""
    signals = list(signals)
    appointed = {s.raw_name for s in signals if s.kind == "appointed"}
    return [
        replace(s, paired_appointment=True)
        if s.kind in NEUTRAL_DEPARTURE_KINDS and s.raw_name in appointed
        else s
        for s in signals
    ]


def _plausible_name(name: str) -> bool:
    if "·" in name:          # transliterated minority name
        return 3 <= len(name) <= 12
    if not 2 <= len(name) <= 4:
        return False
    if not all("一" <= ch <= "鿿" for ch in name):
        return False
    return name[:2] in _SURNAMES_2 or name[0] in _SURNAMES_1


def _span_around(text: str, start: int, end: int) -> str:
    """The clause containing a match, for the audit trail."""
    left = max((text.rfind(ch, 0, start) for ch in "。；\n"), default=-1)
    right = min(
        (pos for pos in (text.find(ch, end) for ch in "。；\n") if pos != -1),
        default=len(text),
    )
    return text[left + 1: right].strip()[:_MAX_SPAN]


# ------------------------------------------------------------------ internals --

def _segments(text: str) -> list[str]:
    return [s.strip() for s in _SEGMENT_SPLIT.split(text) if len(s.strip()) > 4]


def _document_subject(haystack: str, known_names: set[str]) -> str | None:
    """The known name mentioned most often in the document, if any."""
    counts = {n: haystack.count(n) for n in known_names}
    counts = {n: c for n, c in counts.items() if c}
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: (kv[1], len(kv[0])))[0]


def _subject_for(
    segment: str, trigger_idx: int, known_names: set[str]
) -> tuple[str | None, bool]:
    """Nearest known name before the trigger, else a surname-anchored guess."""
    prefix = segment[:trigger_idx]

    best_name, best_pos = None, -1
    for name in known_names:
        pos = prefix.rfind(name)
        if pos > best_pos:
            best_name, best_pos = name, pos
    if best_name is not None and best_pos >= 0:
        return best_name, False

    return _guess_name(_before_subject_marker(prefix)), True


def _before_subject_marker(prefix: str) -> str:
    """Trim `prefix` at the earliest subject marker, so the name we read
    backwards from is the one the clause is actually about."""
    positions = [prefix.find(m) for m in _SUBJECT_MARKERS]
    positions = [p for p in positions if p > 0]
    return prefix[: min(positions)] if positions else prefix


def _guess_name(prefix: str) -> str | None:
    """Read backwards from the end of `prefix` for a 2-4 character name whose
    leading character(s) are a known surname."""
    window = prefix[-6:]
    if not window:
        return None
    for length in (4, 3, 2):
        if len(window) < length:
            continue
        candidate = window[-length:]
        if not all("一" <= ch <= "鿿" for ch in candidate):
            continue
        is_surname = candidate[:2] in _SURNAMES_2 or candidate[0] in _SURNAMES_1
        if not is_surname:
            continue
        # Reject when the character immediately before looks like part of a name
        # rather than the tail of a job title -- that means we cut in the wrong
        # place and are about to slice a longer word in half.
        before = window[-length - 1] if len(window) > length else ""
        if before and before not in _TITLE_TAIL and "一" <= before <= "鿿":
            if before in _SURNAMES_1:
                continue
        return candidate
    return None


def _position_before(segment: str, name: str) -> str | None:
    idx = segment.find(name)
    if idx <= 0:
        return None
    raw = segment[:idx].strip("，,、 ")
    return raw[-60:] or None
