from __future__ import annotations

from pathlib import Path

import pytest

from cadre import db
from cadre.config import Config
from cadre.sources import Fetcher

FIXTURES = Path(__file__).parent / "fixtures"

SEED = [
    ("唐仁健", 3),
    ("李晓鹏", 4),
    ("秦刚", 2),
]


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        data_dir=tmp_path,
        db_path=tmp_path / "cadre.db",
        archive_dir=tmp_path / "archive",
        user_agent="cadre-watch/test",
        request_timeout=5.0,
        delay_between_requests=0.0,
        max_listing_pages=1,
        offline=True,
    )


@pytest.fixture
def conn(cfg: Config):
    cfg.ensure_dirs()
    connection = db.connect(cfg.db_path)
    db.migrate(connection)
    for name, tier in SEED:
        cur = connection.execute("INSERT INTO person (name_zh) VALUES (?)", (name,))
        connection.execute(
            "INSERT INTO watchlist (person_id, tier) VALUES (?, ?)", (cur.lastrowid, tier)
        )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def fetcher(cfg: Config):
    with Fetcher(
        user_agent=cfg.user_agent, timeout=cfg.request_timeout,
        delay=0.0, offline=True, fixture_dir=FIXTURES,
    ) as f:
        yield f
