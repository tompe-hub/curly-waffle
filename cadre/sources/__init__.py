from cadre.sources.base import FetchedDoc, Fetcher, Link, Source
from cadre.sources.ccdi import CcdiSource
from cadre.sources.cms import CmsSource
from cadre.sources.npc import NpcSource
from cadre.sources.statecouncil import StateCouncilSource

ALL_SOURCES: list[Source] = [
    CcdiSource(),
    NpcSource(),
    StateCouncilSource(),
]

ENABLED_SOURCES: list[Source] = [s for s in ALL_SOURCES if s.enabled]

__all__ = [
    "FetchedDoc", "Link", "Source", "Fetcher", "CmsSource",
    "CcdiSource", "NpcSource", "StateCouncilSource",
    "ALL_SOURCES", "ENABLED_SOURCES",
]
