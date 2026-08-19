"""The selector diagnostic. Site redesigns are the expected failure mode of
this whole system, so a stale selector has to produce a fix, not a shrug."""
from __future__ import annotations

from cadre.sources.base import suggest_body_selectors, suggest_list_selectors
from cadre.sources.cms import DEFAULT_ARTICLE_HREF

LISTING = """
<html><body>
  <div class="nav"><a href="/">首页</a></div>
  <div class="redesigned"><ul class="brand-new-list">
    <li class="row"><a href="/scdcn/zggb/202405/t20240518_330001.shtml">甲</a></li>
    <li class="row"><a href="/scdcn/zggb/202401/t20240116_320002.shtml">乙</a></li>
    <li class="row"><a href="/scdcn/zggb/202403/t20240301_330099.shtml">丙</a></li>
  </ul></div>
</body></html>
"""

ARTICLE = """
<html><body>
  <div class="sidebar">导航</div>
  <div class="brand-new-body"><p>农业农村部党组书记、部长唐仁健涉嫌严重违纪违法，
  目前正接受中央纪委国家监委纪律审查和监察调查。这是一段足够长的正文内容，
  用于确认正文选择器能够按中文字符数量被正确识别出来。</p></div>
</body></html>
"""


def test_listing_selectors_are_proposed_when_the_old_ones_miss():
    suggestions = suggest_list_selectors(
        LISTING, "https://www.ccdi.gov.cn/scdcn/zggb/", DEFAULT_ARTICLE_HREF
    )
    assert suggestions
    selectors = [s for s, _ in suggestions]
    assert "li.row" in selectors
    # the row element holding all three links should rank at or near the top
    assert suggestions[0][1] == 3


def test_navigation_links_are_not_proposed():
    selectors = [s for s, _ in suggest_list_selectors(
        LISTING, "https://www.ccdi.gov.cn/scdcn/zggb/", DEFAULT_ARTICLE_HREF
    )]
    assert "div.nav" not in selectors


def test_body_selector_is_found_by_chinese_character_density():
    suggestions = suggest_body_selectors(ARTICLE)
    assert suggestions
    assert suggestions[0][0] == "div.brand-new-body"


def test_no_suggestions_when_nothing_looks_like_an_article():
    empty = "<html><body><a href='/about.html'>关于</a></body></html>"
    assert suggest_list_selectors(empty, "https://x.invalid/", DEFAULT_ARTICLE_HREF) == []
