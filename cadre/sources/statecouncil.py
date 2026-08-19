"""国务院 · 人事任免 -- State Council personnel notices on gov.cn.

Covers ministerial and vice-ministerial appointments and removals. Same 任免
language as the NPC source, published after State Council executive meetings.

  URLs and selectors are UNVERIFIED -- run `cadre check-source state_council`.
"""
from __future__ import annotations

from cadre.sources.cms import CmsSource


class StateCouncilSource(CmsSource):
    id = "state_council"
    name = "国务院 · 人事任免"

    LISTINGS = [
        "https://www.gov.cn/zhengce/renshi/",
        "https://www.gov.cn/guowuyuan/renmian.htm",
    ]
