"""Feed source definitions.

Sources live in ``config/feeds.json`` so the list can be edited without touching
code. Each source is normalised into a :class:`Feed` for the rest of the app.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "feeds.json"

VALID_REGIONS = {"china", "global"}


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    region: str  # "china" or "global"
    tags: tuple[str, ...] = field(default_factory=tuple)  # forced tags, e.g. ("ai",)


def load_feeds(path: Path | str = CONFIG_PATH) -> list[Feed]:
    """Read and validate the feed list from JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    feeds: list[Feed] = []
    for entry in data.get("feeds", []):
        region = entry.get("region", "global")
        if region not in VALID_REGIONS:
            raise ValueError(f"Feed {entry.get('name')!r} has invalid region {region!r}")
        feeds.append(
            Feed(
                name=entry["name"],
                url=entry["url"],
                region=region,
                tags=tuple(entry.get("tags", [])),
            )
        )
    return feeds
