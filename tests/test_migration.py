"""Upgrading an existing database.

Every other test starts from a fresh database, which structurally cannot catch
a migration that only breaks on upgrade -- and one did: an index declared in
schema.sql over a column that only exists after the ALTERs run, leaving anyone
with an older database unable to open the dashboard at all.
"""
from __future__ import annotations

import sqlite3

from cadre import db
from cadre.importers import import_roster
from tests.test_import import CPED


def _v0_database(path):
    """A database as it was before external_id / source_dataset existed."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE person (
            id INTEGER PRIMARY KEY, name_zh TEXT NOT NULL, name_pinyin TEXT,
            birth_year INTEGER, birth_month INTEGER, sex TEXT, native_place TEXT,
            ethnicity TEXT, notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT
        );
        INSERT INTO person (name_zh, birth_year) VALUES ('唐仁健', 1962);
        """
    )
    conn.commit()
    return conn


def test_an_old_database_upgrades_in_place(tmp_path):
    path = tmp_path / "old.db"
    conn = _v0_database(path)

    db.migrate(conn)     # must not raise

    columns = {r["name"] for r in conn.execute("PRAGMA table_info(person)")}
    assert {"external_id", "source_dataset"} <= columns
    # existing rows survive
    assert conn.execute("SELECT COUNT(*) FROM person").fetchone()[0] == 1


def test_migrating_twice_is_a_no_op(tmp_path):
    path = tmp_path / "old.db"
    conn = _v0_database(path)
    db.migrate(conn)
    db.migrate(conn)     # idempotent
    assert conn.execute("SELECT COUNT(*) FROM person").fetchone()[0] == 1


def test_an_upgraded_database_can_still_import(tmp_path):
    path = tmp_path / "old.db"
    conn = _v0_database(path)
    db.migrate(conn)
    report = import_roster(conn, CPED)
    assert report.people_created >= 1
    # the pre-existing 唐仁健 row carries the same birth year and no external
    # id, so the import adopts it rather than creating a second person
    assert report.people_adopted == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM person WHERE name_zh = '唐仁健'"
    ).fetchone()[0] == 1
    adopted = conn.execute(
        "SELECT * FROM person WHERE name_zh = '唐仁健'").fetchone()
    assert adopted["external_id"] == "C0001"
    assert adopted["source_dataset"] == "cped"
