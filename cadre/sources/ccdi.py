"""中央纪委国家监委 (CCDI / NSC) discipline-inspection announcements.

The highest-value source in the system: purge announcements are dated,
attributed, and written in near-boilerplate language, so they parse
deterministically with no LLM in the loop.

  The URLs and selectors below have NOT been verified against a live fetch --
  development happened in a sandbox whose network policy blocks ccdi.gov.cn.
  Run `cadre check-source ccdi` before trusting a run; when a selector misses,
  it reads the returned HTML and prints the ones that would work.
"""
from __future__ import annotations

from cadre.sources.cms import CmsSource


class CcdiSource(CmsSource):
    id = "ccdi"
    name = "中央纪委国家监委 · 审查调查"

    # 审查调查 channel and its two cadre tiers. 中管干部 (centrally-managed
    # cadres) is the tier that matters for a Central Committee watchlist;
    # 省管干部 is the provincial tier and much higher volume.
    LISTINGS = [
        "https://www.ccdi.gov.cn/scdcn/zggb/",   # 中管干部
        "https://www.ccdi.gov.cn/scdcn/sggb/",   # 省管干部
        "https://www.ccdi.gov.cn/scdcn/",        # channel index
    ]
