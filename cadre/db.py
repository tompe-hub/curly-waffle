"""SQLite access. One writer (the daily job), many readers (the dashboard),
which is exactly what WAL mode is for."""
from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path
from typing import Iterable


def connect(db_path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if read_only and db_path.exists():
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not read_only:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Apply schema.sql. It is written to be idempotent, so this doubles as
    both create-from-scratch and a no-op on an existing database."""
    sql = resources.files("cadre").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def fetchall(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def fetchone(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
    return conn.execute(sql, tuple(params)).fetchone()
