"""Sources scoped for v1, implemented to the same interface but disabled.

Each one is a listing page plus an article body, exactly like CCDI -- the work
is finding the right selectors and writing the extraction rules for the
appointment/removal (任免) language, which is a different lexicon from the
discipline-inspection language.
"""
from __future__ import annotations

from cadre.sources.base import FetchedDoc, Link


class _Unimplemented:
    enabled = False

    def listing_urls(self) -> list[str]:
        raise NotImplementedError(f"{self.id} source is not implemented yet")

    def parse_listing(self, html: str, base_url: str) -> list[Link]:
        raise NotImplementedError(f"{self.id} source is not implemented yet")

    def parse_article(self, html: str, link: Link) -> FetchedDoc:
        raise NotImplementedError(f"{self.id} source is not implemented yet")


class NpcSource(_Unimplemented):
    """全国人大常委会 appointment/removal decisions (任免).

    Authoritative record for state-side transitions. Publishes in bursts on the
    closing day of each bimonthly session, so this source should be scheduled
    against the NPCSC calendar rather than polled evenly."""
    id = "npc"
    name = "全国人大常委会 · 任免"


class StateCouncilSource(_Unimplemented):
    """国务院 人事任免 notices on gov.cn -- ministerial and vice-ministerial."""
    id = "state_council"
    name = "国务院 · 人事任免"
