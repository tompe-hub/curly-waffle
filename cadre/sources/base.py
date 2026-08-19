"""Source interface and the polite fetcher.

A Source knows three things: which listing pages to poll, how to pull article
links out of a listing, and how to turn an article page into text. Everything
else -- politeness, archiving, dedup -- is handled once, here.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

_WS = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class Link:
    url: str
    title: str
    published_at: str | None = None


@dataclass
class FetchedDoc:
    source_id: str
    url: str
    title: str
    published_at: str | None
    raw_html: str
    text: str


class Source(Protocol):
    id: str
    name: str
    enabled: bool

    def listing_urls(self) -> list[str]: ...
    def parse_listing(self, html: str, base_url: str) -> list[Link]: ...
    def parse_article(self, html: str, link: Link) -> FetchedDoc: ...


# ------------------------------------------------------------------ helpers --

def clean_text(node_html: str) -> str:
    """Visible text with script/style stripped and whitespace collapsed."""
    tree = HTMLParser(node_html)
    for tag in ("script", "style", "noscript"):
        for node in tree.css(tag):
            node.decompose()
    body = tree.body or tree.root
    if body is None:
        return ""
    text = body.text(separator="\n")
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANKS.sub("\n\n", text).strip()


_DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})"),
    re.compile(r"(20\d{2})[-/年](\d{1,2})月?$"),
]


def parse_cn_date(raw: str | None) -> str | None:
    """Normalise the date formats Chinese government CMSes emit
    (2025-03-14, 2025/03/14, 2025年03月14日) to ISO. Returns None if absent."""
    if not raw:
        return None
    for pat in _DATE_PATTERNS:
        m = pat.search(raw)
        if not m:
            continue
        parts = m.groups()
        if len(parts) == 3:
            y, mo, d = parts
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        y, mo = parts
        return f"{int(y):04d}-{int(mo):02d}-01"
    return None


def absolutise(base_url: str, href: str) -> str:
    return urljoin(base_url, href.strip())


# ------------------------------------------------------------------ fetcher --

class Fetcher:
    """Sequential, rate-limited HTTP with an offline fixture mode.

    Offline mode exists because the extraction and resolution layers are the
    parts worth testing, and they should be testable without touching the
    network or depending on what a government site happens to be serving today.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float,
        delay: float,
        offline: bool = False,
        fixture_dir: Path | None = None,
    ) -> None:
        self.delay = delay
        self.offline = offline
        self.fixture_dir = fixture_dir
        self._last_request = 0.0
        self._client: httpx.Client | None = None
        if not offline:
            self._client = httpx.Client(
                headers={"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9"},
                timeout=timeout,
                follow_redirects=True,
            )

    def get(self, url: str) -> str:
        if self.offline:
            return self._from_fixture(url)
        assert self._client is not None
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        resp = self._client.get(url)
        self._last_request = time.monotonic()
        resp.raise_for_status()
        # Government sites frequently mislabel or omit the charset; sniffing the
        # declared meta charset via httpx's own detection is more reliable than
        # trusting the header.
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.default_encoding = "utf-8"
        return resp.text

    def _from_fixture(self, url: str) -> str:
        if self.fixture_dir is None:
            raise RuntimeError("offline fetcher needs a fixture_dir")
        name = re.sub(r"[^A-Za-z0-9]+", "_", url).strip("_")[-120:]
        path = self.fixture_dir / f"{name}.html"
        if not path.exists():
            raise FileNotFoundError(f"no fixture for {url} (looked for {path})")
        return path.read_text(encoding="utf-8")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
