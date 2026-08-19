"""中央纪委国家监委 (CCDI / NSC) discipline-inspection announcements.

This is the highest-value source in the system: purge announcements are dated,
attributed, and written in near-boilerplate language, which means they can be
parsed deterministically without an LLM in the loop.

  IMPORTANT -- the listing paths and CSS selectors below are the shapes these
  CMS pages have historically used, but they have NOT been verified against a
  live fetch (this was developed in a sandbox whose network policy blocks
  ccdi.gov.cn). Run `cadre check-source ccdi` on a machine with real network
  access before trusting a run; it reports what each selector matched so you
  can correct LISTINGS / _LIST_CONTAINERS / _BODY_SELECTORS in one place.
"""
from __future__ import annotations

import re

from cadre.sources.base import (
    FetchedDoc,
    Link,
    absolutise,
    clean_text,
    parse_cn_date,
)
from selectolax.parser import HTMLParser

# 审查调查 channel and its two cadre tiers. 中管干部 (centrally-managed cadres)
# is the one that matters for a Central Committee watchlist; 省管干部 is the
# provincial tier and is much higher volume.
LISTINGS = [
    "https://www.ccdi.gov.cn/scdcn/zggb/",   # 中管干部
    "https://www.ccdi.gov.cn/scdcn/sggb/",   # 省管干部
    "https://www.ccdi.gov.cn/scdcn/",        # channel index, catches the rest
]

# Tried in order; first one that yields links wins.
_LIST_CONTAINERS = [
    "ul.list_news li",
    "div.list_news li",
    "div.tab_cont li",
    "ul.list li",
    "div.content li",
    "li",
]

_BODY_SELECTORS = [
    "div.content",
    "div.TRS_Editor",
    "div.article_content",
    "div#detail",
    "div.detail",
    "article",
]

# An article URL on these CMSes carries a yyyymm path segment and a .shtml/.html
# leaf. Anything else in the list markup is navigation chrome.
_ARTICLE_HREF = re.compile(r"/20\d{2}\d{2}/.*\.s?html?$|/t20\d{6}_\d+\.s?html?$")


class CcdiSource:
    id = "ccdi"
    name = "中央纪委国家监委 · 审查调查"
    enabled = True

    def listing_urls(self) -> list[str]:
        return list(LISTINGS)

    def parse_listing(self, html: str, base_url: str) -> list[Link]:
        tree = HTMLParser(html)
        for selector in _LIST_CONTAINERS:
            links = self._links_from(tree.css(selector), base_url)
            if links:
                return links
        return []

    @staticmethod
    def _links_from(nodes, base_url: str) -> list[Link]:
        out: list[Link] = []
        seen: set[str] = set()
        for node in nodes:
            anchor = node if node.tag == "a" else node.css_first("a")
            if anchor is None:
                continue
            href = anchor.attributes.get("href")
            if not href or href.startswith(("#", "javascript:")):
                continue
            url = absolutise(base_url, href)
            if not _ARTICLE_HREF.search(url) or url in seen:
                continue
            seen.add(url)
            title = (anchor.attributes.get("title") or anchor.text() or "").strip()
            # The publication date usually sits in a sibling <span>/<em>; fall
            # back to the yyyymm path segment, which is always present.
            date_text = " ".join(
                n.text() for n in node.css("span, em, i") if n.text()
            )
            published = parse_cn_date(date_text) or _date_from_url(url)
            out.append(Link(url=url, title=title, published_at=published))
        return out

    def parse_article(self, html: str, link: Link) -> FetchedDoc:
        tree = HTMLParser(html)
        body_html = None
        for selector in _BODY_SELECTORS:
            node = tree.css_first(selector)
            if node is not None and len(node.text() or "") > 80:
                body_html = node.html
                break
        text = clean_text(body_html if body_html is not None else html)

        title = link.title
        if not title:
            h = tree.css_first("h1") or tree.css_first("title")
            title = (h.text() if h else "").strip()

        published = link.published_at or parse_cn_date(text[:400]) or _date_from_url(link.url)
        return FetchedDoc(
            source_id=self.id,
            url=link.url,
            title=title,
            published_at=published,
            raw_html=html,
            text=text,
        )


_URL_DATE = re.compile(r"/(20\d{2})(\d{2})/")


def _date_from_url(url: str) -> str | None:
    m = _URL_DATE.search(url)
    return f"{m.group(1)}-{m.group(2)}-01" if m else None
