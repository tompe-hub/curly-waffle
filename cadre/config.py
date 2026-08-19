"""Runtime configuration. Everything is overridable by environment variable so
the same code runs from cron, from the CLI, and from tests."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _root() -> Path:
    return Path(os.environ.get("CADRE_DATA", "./data")).resolve()


@dataclass(frozen=True)
class Config:
    data_dir: Path
    db_path: Path
    archive_dir: Path
    user_agent: str
    request_timeout: float
    delay_between_requests: float   # politeness, per host
    max_listing_pages: int
    offline: bool                   # serve fetches from tests/fixtures instead of network

    @classmethod
    def load(cls) -> "Config":
        root = _root()
        return cls(
            data_dir=root,
            db_path=Path(os.environ.get("CADRE_DB", root / "cadre.db")),
            archive_dir=Path(os.environ.get("CADRE_ARCHIVE", root / "archive")),
            user_agent=os.environ.get(
                "CADRE_UA",
                "cadre-watch/0.1 (research monitor; +https://example.invalid/cadre)",
            ),
            request_timeout=float(os.environ.get("CADRE_TIMEOUT", "30")),
            delay_between_requests=float(os.environ.get("CADRE_DELAY", "2.0")),
            max_listing_pages=int(os.environ.get("CADRE_MAX_PAGES", "3")),
            offline=os.environ.get("CADRE_OFFLINE", "") not in ("", "0", "false"),
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
