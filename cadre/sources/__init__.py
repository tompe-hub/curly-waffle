from cadre.sources.base import FetchedDoc, Link, Source, Fetcher
from cadre.sources.ccdi import CcdiSource
from cadre.sources.stubs import NpcSource, StateCouncilSource

ALL_SOURCES: list[Source] = [
    CcdiSource(),
    NpcSource(),
    StateCouncilSource(),
]

ENABLED_SOURCES: list[Source] = [s for s in ALL_SOURCES if s.enabled]

__all__ = [
    "FetchedDoc", "Link", "Source", "Fetcher",
    "CcdiSource", "NpcSource", "StateCouncilSource",
    "ALL_SOURCES", "ENABLED_SOURCES",
]
