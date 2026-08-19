"""Content-addressed archive of every document we have ever seen.

The database is a derived artifact: it can be rebuilt by replaying extraction
over this directory. That is what makes it safe to fix a parser after the fact
and recover events we originally mis-read, and it is the only reason
scrub detection can work at all.
"""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path


def text_digest(text: str) -> str:
    """Hash the extracted text, not the raw bytes. Government CMS markup churns
    session ids and render timestamps on every request; hashing raw HTML would
    make every fetch look like a change."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _path_for(archive_dir: Path, digest: str) -> Path:
    # Two levels of fan-out keeps directory sizes sane over years of daily runs.
    return archive_dir / digest[:2] / digest[2:4] / f"{digest}.html.gz"


def store(archive_dir: Path, digest: str, raw_html: str) -> str:
    """Write raw HTML gzipped. Returns the archive-relative path.
    Idempotent: same digest, same path, no rewrite."""
    dest = _path_for(archive_dir, digest)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            fh.write(raw_html)
        tmp.replace(dest)
    return str(dest.relative_to(archive_dir))


def load(archive_dir: Path, rel_path: str) -> str:
    with gzip.open(archive_dir / rel_path, "rt", encoding="utf-8") as fh:
        return fh.read()
