"""全国人大常委会 · 任免 -- NPC Standing Committee appointment and removal
decisions.

The authoritative record for state-side transitions. Two things make this
source behave differently from CCDI:

  * It publishes in bursts. The NPCSC meets roughly bimonthly and issues its
    personnel decisions on the closing day, so the useful scheduling unit is
    the session calendar, not an even daily poll. A daily run catches them
    anyway; it is just idle most of the time.

  * One document names many people. A single decision can appoint and remove
    dozens, which is why this source relies on the pattern lexicon rather than
    the single-subject path CCDI uses.

  URLs and selectors are UNVERIFIED -- run `cadre check-source npc`.
"""
from __future__ import annotations

from cadre.sources.cms import CmsSource


class NpcSource(CmsSource):
    id = "npc"
    name = "全国人大常委会 · 任免"

    LISTINGS = [
        "http://www.npc.gov.cn/npc/c2/c30834/",   # 任免 decisions
        "http://www.npc.gov.cn/npc/c2/c30836/",   # 常委会公报 personnel section
    ]
