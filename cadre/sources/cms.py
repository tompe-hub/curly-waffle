"""Shared base for Chinese government CMS sources.

CCDI, the NPC and the State Council all publish the same shape: a paginated
listing of dated links, and article pages with the text in one dense block. The
differences are the URLs and the class names, so those are the only things a
subclass has to state.

Each subclass's selectors are declared as class attributes rather than buried
in methods, because they are the part that breaks when a site is redesigned and
`cadre check-source <id>` needs to be able to point at exactly one place.
"""
from __future__ import annotations

import re

from selectolax.parser import HTMLParser

from cadre.sources.base import (
    FetchedDoc,
    Link,
    absolutise,
    clean_text,
    parse_cn_date,
)

# An article URL on these CMSes carries a yyyymm path segment and a .shtml/.html
# leaf; navigation chrome does not.
DEFAULT_ARTICLE_HREF = re.compile(
    r"/20\d{2}[-_]?\d{2}/.*\.s?html?$|/t20\d{6}_\d+\.s?html?$|/content_\d+\.htm$"
)

DEFAULT_LIST_CONTAINERS = [
    "ul.list_news li", "div.list_news li", "div.tab_cont li",
    "ul.list li", "div.list li", "div.content li", "li",
]

DEFAULT_BODY_SELECTORS = [
    "div.content", "div.TRS_Editor", "div.article_content", "div.pages_content",
    "div#UCAP-CONTENT", "div#detail", "div.detail", "article",
]

_URL_DATE = re.compile(r"/(20\d{2})[-_]?(\d{2})/")


class CmsSource:
    id: str = ""
    name: str = ""
    enabled: bool = True

    LISTINGS: list[str] = []
    LIST_CONTAINERS: list[str] = DEFAULT_LIST_CONTAINERS
    BODY_SELECTORS: list[str] = DEFAULT_BODY_SELECTORS
    ARTICLE_HREF: re.Pattern = DEFAULT_ARTICLE_HREF

    # consumed by `cadre check-source` when it proposes replacements
    @property
    def article_pattern(self) -> re.Pattern:
        return self.ARTICLE_HREF

    @property
    def body_selectors(self) -> list[str]:
        return self.BODY_SELECTORS

    def listing_urls(self) -> list[str]:
        return list(self.LISTINGS)

    def parse_listing(self, html: str, base_url: str) -> list[Link]:
        tree = HTMLParser(html)
        for selector in self.LIST_CONTAINERS:
            links = self._links_from(tree.css(selector), base_url)
            if links:
                return links
        return []

    def _links_from(self, nodes, base_url: str) -> list[Link]:
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
            if not self.ARTICLE_HREF.search(url) or url in seen:
                continue
            seen.add(url)
            title = (anchor.attributes.get("title") or anchor.text() or "").strip()
            date_text = " ".join(n.text() for n in node.css("span, em, i") if n.text())
            out.append(Link(
                url=url,
                title=title,
                published_at=parse_cn_date(date_text) or date_from_url(url),
            ))
        return out

    def parse_article(self, html: str, link: Link) -> FetchedDoc:
        tree = HTMLParser(html)
        body_html = None
        for selector in self.BODY_SELECTORS:
            node = tree.css_first(selector)
            if node is not None and len(node.text() or "") > 80:
                body_html = node.html
                break
        text = clean_text(body_html if body_html is not None else html)

        title = link.title
        if not title:
            heading = tree.css_first("h1") or tree.css_first("title")
            title = (heading.text() if heading else "").strip()

        return FetchedDoc(
            source_id=self.id,
            url=link.url,
            title=title,
            published_at=(
                link.published_at
                or parse_cn_date(text[:400])
                or date_from_url(link.url)
            ),
            raw_html=html,
            text=text,
        )


def date_from_url(url: str) -> str | None:
    m = _URL_DATE.search(url)
    return f"{m.group(1)}-{m.group(2)}-01" if m else None
