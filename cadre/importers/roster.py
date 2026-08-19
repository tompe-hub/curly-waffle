"""Roster import -- CPED, Wikidata, or any tabular file of officials.

Why this is mapping-driven rather than hardcoded to CPED's schema: research
datasets are versioned, reshaped, and redistributed, and CPED in particular
ships in several formats. An importer that assumed a fixed set of column names
would not fail loudly on a mismatch -- it would silently map the wrong field,
which is the worst outcome available. So instead:

  * columns are matched against alias lists, normalised for case and
    separators, and anything unmatched is reported rather than guessed at;
  * `--dry-run` shows exactly what would be written before anything is;
  * near-miss column names get a "did you mean" suggestion;
  * `--map field=column` overrides anything the aliases miss.

The same importer therefore handles a Wikidata export, a China Vitae scrape or
a hand-built CSV, not just one dataset's current layout.

One row is one person-position spell. Files with no position columns import as
people only; files with them also populate org, position and spell.
"""
from __future__ import annotations

import csv
import difflib
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from cadre.importers.ranks import is_sideline, rank_score, tier_for

FIELDS = [
    "external_id", "name_zh", "name_pinyin", "birth_year", "birth_month",
    "sex", "native_place", "ethnicity", "cc_status", "rank",
    "org", "position_title", "start_date", "end_date",
]

REQUIRED_FIELDS = ["name_zh"]

# Spellings seen across CPED-style datasets, Wikidata SPARQL exports and
# hand-rolled sheets, in both English and Chinese.
ALIASES: dict[str, list[str]] = {
    "external_id": ["id", "pid", "person_id", "cped_id", "uid", "qid",
                    "wikidata_id", "item", "person"],
    "name_zh": ["name_zh", "姓名", "名字", "chinese_name", "name_chinese",
                "name_cn", "cname", "name", "personlabel", "官员姓名"],
    "name_pinyin": ["name_pinyin", "pinyin", "name_py", "py", "name_en",
                    "english_name", "name_english", "romanization", "ename", "拼音"],
    "birth_year": ["birth_year", "birthyear", "byear", "出生年", "出生年份",
                   "yob", "dob_year", "born", "birth"],
    "birth_month": ["birth_month", "birthmonth", "bmonth", "出生月", "出生月份"],
    "sex": ["sex", "gender", "性别"],
    "native_place": ["native_place", "nativeplace", "籍贯", "birthplace",
                     "place_of_birth", "origin", "native"],
    "ethnicity": ["ethnicity", "民族", "ethnic_group", "ethnic", "nationality_ethnic"],
    "cc_status": ["cc_status", "ccstatus", "central_committee", "cc_member",
                  "cc_rank", "中央委员会", "中委", "committee_status",
                  "politburo", "cc"],
    "rank": ["rank", "admin_rank", "adminrank", "行政级别", "级别", "level",
             "bureaucratic_rank", "rank_level", "grade"],
    "org": ["org", "organization", "organisation", "单位", "机构", "agency",
            "institution", "employer", "department", "unit", "work_unit"],
    "position_title": ["position", "position_title", "title", "职务", "post",
                       "job_title", "positionlabel", "office", "职位"],
    "start_date": ["start_date", "startdate", "start", "begin", "from",
                   "任职开始", "start_year", "startyear", "year_start", "date_start"],
    "end_date": ["end_date", "enddate", "end", "until", "to", "任职结束",
                 "end_year", "endyear", "year_end", "date_end"],
}

_NORM = re.compile(r"[\s\-_.·()（）]+")
_ALIAS_INDEX = {
    _NORM.sub("", alias).lower(): fname
    for fname, aliases in ALIASES.items()
    for alias in aliases
}


def _norm(text: str) -> str:
    return _NORM.sub("", str(text)).lower()


# --------------------------------------------------------------- mapping ----

@dataclass
class Mapping:
    resolved: dict[str, str] = field(default_factory=dict)   # field -> column
    unmatched_fields: list[str] = field(default_factory=list)
    unused_columns: list[str] = field(default_factory=list)
    suggestions: dict[str, str] = field(default_factory=dict)  # field -> column

    @property
    def ok(self) -> bool:
        return all(f in self.resolved for f in REQUIRED_FIELDS)

    @property
    def has_spells(self) -> bool:
        return "position_title" in self.resolved or "org" in self.resolved


def resolve_mapping(columns: list[str], overrides: dict[str, str] | None = None) -> Mapping:
    """Match file columns to our fields. Explicit overrides always win.

    Matching is exact on the normalised name -- never fuzzy. A wrong automatic
    match is silent and permanent; an unmatched column is visible and fixable,
    so unmatched is the safer failure."""
    overrides = overrides or {}
    mapping = Mapping()
    taken: set[str] = set()

    for fname, column in overrides.items():
        if fname not in FIELDS:
            raise ValueError(f"unknown field {fname!r}; known fields: {', '.join(FIELDS)}")
        if column not in columns:
            raise ValueError(f"column {column!r} is not in the file")
        mapping.resolved[fname] = column
        taken.add(column)

    for column in columns:
        if column in taken:
            continue
        fname = _ALIAS_INDEX.get(_norm(column))
        if fname and fname not in mapping.resolved:
            mapping.resolved[fname] = column
            taken.add(column)

    mapping.unmatched_fields = [f for f in FIELDS if f not in mapping.resolved]
    mapping.unused_columns = [c for c in columns if c not in taken]

    # Near-miss hints, so an unrecognised header is a one-line --map away.
    for fname in mapping.unmatched_fields:
        pool = {c: _norm(c) for c in mapping.unused_columns}
        candidates = difflib.get_close_matches(
            fname, list(pool.values()), n=1, cutoff=0.6
        )
        if candidates:
            mapping.suggestions[fname] = next(
                c for c, n in pool.items() if n == candidates[0]
            )
    return mapping


# ----------------------------------------------------------------- dates ----

_DATE = re.compile(r"(1|2)(\d{3})[-/年]?(\d{1,2})?[-/月]?(\d{1,2})?")


def parse_date(raw) -> tuple[str | None, str | None]:
    """Return (ISO date, precision). Roster data is full of bare years and
    year-months; recording the precision keeps that honest instead of
    inventing a January the first."""
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text or text.lower() in {"na", "n/a", "null", "none", "-", "."}:
        return None, None
    m = _DATE.match(text)
    if not m:
        return None, None
    year = int(m.group(1) + m.group(2))
    if not 1900 <= year <= 2100:
        return None, None
    month, day = m.group(3), m.group(4)
    if month and day:
        return f"{year:04d}-{int(month):02d}-{int(day):02d}", "day"
    if month:
        return f"{year:04d}-{int(month):02d}-01", "month"
    return f"{year:04d}-01-01", "year"


def _int_or_none(raw) -> int | None:
    if raw is None:
        return None
    m = re.search(r"\d{1,4}", str(raw))
    return int(m.group()) if m else None


# ---------------------------------------------------------------- report ----

@dataclass
class ImportReport:
    rows_read: int = 0
    rows_skipped: int = 0
    people_created: int = 0
    people_updated: int = 0
    people_adopted: int = 0
    orgs_created: int = 0
    positions_created: int = 0
    spells_created: int = 0
    watchlisted: int = 0
    tier_counts: dict[int, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False

    def lines(self) -> list[str]:
        out = [
            f"rows read          {self.rows_read}",
            f"rows skipped       {self.rows_skipped}",
            f"people created     {self.people_created}",
            f"people updated     {self.people_updated}",
            f"people adopted     {self.people_adopted}   "
            f"(pre-existing rows claimed by this dataset)",
            f"orgs created       {self.orgs_created}",
            f"positions created  {self.positions_created}",
            f"spells created     {self.spells_created}",
            f"watchlisted        {self.watchlisted}",
        ]
        for tier in sorted(self.tier_counts):
            out.append(f"  tier {tier}            {self.tier_counts[tier]}")
        return out


# ---------------------------------------------------------------- reading ---

def read_rows(path: Path, encoding: str = "utf-8") -> tuple[list[str], list[dict]]:
    if path.suffix.lower() == ".dta":
        raise ValueError(
            "Stata (.dta) files are not read directly -- convert first:\n"
            "    pip install pandas pyreadstat\n"
            f"    python -c \"import pandas as pd; "
            f"pd.read_stata('{path}').to_csv('{path.with_suffix('.csv')}', index=False)\""
        )
    delimiter = "\t" if path.suffix.lower() in (".tsv", ".tab") else ","
    with path.open(encoding=encoding, newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    return columns, rows


def inspect_file(path: Path, overrides=None, encoding="utf-8") -> tuple[Mapping, list[dict], list[str]]:
    columns, rows = read_rows(path, encoding)
    return resolve_mapping(columns, overrides), rows, columns


# --------------------------------------------------------------- importing --

def import_roster(
    conn: sqlite3.Connection,
    path: Path,
    *,
    overrides: dict[str, str] | None = None,
    dataset: str = "cped",
    max_tier: int = 3,
    dry_run: bool = False,
    encoding: str = "utf-8",
) -> ImportReport:
    """Import a roster file.

    max_tier controls the WATCHLIST only. Everyone in the file becomes a
    `person` row regardless, because recognising a name during extraction is
    useful even for someone you are not actively watching -- that is what turns
    an unresolved review-queue item into a resolved signal.
    """
    mapping, rows, _ = inspect_file(path, overrides, encoding)
    if not mapping.ok:
        missing = ", ".join(f for f in REQUIRED_FIELDS if f not in mapping.resolved)
        raise ValueError(f"cannot import: no column matched {missing}")

    report = ImportReport(dry_run=dry_run)
    get = lambda row, fname: (row.get(mapping.resolved[fname]) or "").strip() \
        if fname in mapping.resolved else ""

    # tier is a property of the person, not the row: take the most senior
    # standing seen across all of their spells.
    best_tier: dict[int, int] = {}

    savepoint = "cadre_import"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        for row in rows:
            report.rows_read += 1
            name = get(row, "name_zh")
            if not name:
                report.rows_skipped += 1
                continue

            person_id = _upsert_person(conn, row, get, dataset, report)

            tier = tier_for(
                cc_status=get(row, "cc_status") or None,
                rank=get(row, "rank") or None,
                position_title=get(row, "position_title") or None,
            )
            best_tier[person_id] = min(best_tier.get(person_id, 9), tier)

            if mapping.has_spells:
                _insert_spell(conn, person_id, row, get, report)

        for person_id, tier in best_tier.items():
            report.tier_counts[tier] = report.tier_counts.get(tier, 0) + 1
            if tier <= max_tier:
                cur = conn.execute(
                    "INSERT OR REPLACE INTO watchlist (person_id, tier, note) "
                    "VALUES (?, ?, ?)",
                    (person_id, tier, f"imported from {dataset}"),
                )
                report.watchlisted += 1
    finally:
        if dry_run:
            conn.execute(f"ROLLBACK TO {savepoint}")
        conn.execute(f"RELEASE {savepoint}")
        if not dry_run:
            conn.commit()
    return report


def _upsert_person(conn, row, get, dataset: str, report: ImportReport) -> int:
    name = get(row, "name_zh")
    external_id = get(row, "external_id") or None
    birth_year = _int_or_none(get(row, "birth_year"))

    # external_id is the reliable key. Without one, name alone is not enough --
    # homonyms are common -- so birth year is part of the identity.
    found = None
    if external_id:
        found = conn.execute(
            "SELECT id FROM person WHERE source_dataset = ? AND external_id = ?",
            (dataset, external_id),
        ).fetchone()

    if found is None:
        # Adoption. A row already in the database with the same name and birth
        # year, carrying no external id of its own, is this person -- it came
        # from the seed, the review queue, or an earlier import. Creating a
        # second record instead would split their evidence across two person
        # pages, which is both worse and much harder to notice than the rare
        # case this gets wrong (two officials sharing a name AND a birth year).
        # Adoptions are counted in the report so the merge is never silent.
        if birth_year:
            found = conn.execute(
                """SELECT id, external_id FROM person
                    WHERE name_zh = ? AND birth_year = ?
                      AND (external_id IS NULL OR source_dataset = ?)
                    ORDER BY external_id IS NOT NULL DESC LIMIT 1""",
                (name, birth_year, dataset),
            ).fetchone()
        else:
            found = conn.execute(
                """SELECT id, external_id FROM person
                    WHERE name_zh = ? AND birth_year IS NULL
                      AND (external_id IS NULL OR source_dataset = ?)
                    LIMIT 1""",
                (name, dataset),
            ).fetchone()
        if found is not None and external_id and found["external_id"] is None:
            conn.execute(
                "UPDATE person SET external_id = ?, source_dataset = ? WHERE id = ?",
                (external_id, dataset, found["id"]),
            )
            report.people_adopted += 1

    values = {
        "name_pinyin": get(row, "name_pinyin") or None,
        "birth_year": birth_year,
        "birth_month": _int_or_none(get(row, "birth_month")),
        "sex": get(row, "sex") or None,
        "native_place": get(row, "native_place") or None,
        "ethnicity": get(row, "ethnicity") or None,
    }

    if found:
        # Fill gaps, never overwrite: a later row with a blank field must not
        # erase a value an earlier row supplied.
        sets = ", ".join(f"{k} = COALESCE({k}, ?)" for k in values)
        conn.execute(
            f"UPDATE person SET {sets}, updated_at = datetime('now') WHERE id = ?",
            (*values.values(), found["id"]),
        )
        report.people_updated += 1
        return int(found["id"])

    cur = conn.execute(
        """INSERT INTO person
             (name_zh, name_pinyin, birth_year, birth_month, sex, native_place,
              ethnicity, external_id, source_dataset)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, *values.values(), external_id, dataset),
    )
    report.people_created += 1
    return int(cur.lastrowid)


def _insert_spell(conn, person_id: int, row, get, report: ImportReport) -> None:
    title = get(row, "position_title")
    org_name = get(row, "org")
    if not title and not org_name:
        return

    org_id = None
    if org_name:
        found = conn.execute("SELECT id FROM org WHERE name_zh = ?", (org_name,)).fetchone()
        if found:
            org_id = int(found["id"])
        else:
            org_id = int(conn.execute(
                "INSERT INTO org (name_zh) VALUES (?)", (org_name,)
            ).lastrowid)
            report.orgs_created += 1

    title = title or org_name
    found = conn.execute(
        "SELECT id FROM position WHERE title_zh = ? AND org_id IS ?", (title, org_id)
    ).fetchone()
    if found:
        position_id = int(found["id"])
    else:
        raw_rank = get(row, "rank") or None
        # Sideline detection needs the organisation: "副委员长" is meaningless
        # alone, but "全国人民代表大会常务委员会副委员长" is the classic soft
        # landing. The patterns are written against the combined string.
        sideline = is_sideline(f"{org_name}{title}" if org_name else title)
        position_id = int(conn.execute(
            """INSERT INTO position (org_id, title_zh, admin_rank, rank_score, is_sideline)
               VALUES (?, ?, ?, ?, ?)""",
            (org_id, title, raw_rank, rank_score(raw_rank), int(sideline)),
        ).lastrowid)
        report.positions_created += 1

    start, start_prec = parse_date(get(row, "start_date"))
    end, end_prec = parse_date(get(row, "end_date"))

    exists = conn.execute(
        """SELECT 1 FROM spell
            WHERE person_id = ? AND position_id = ? AND start_date IS ?""",
        (person_id, position_id, start),
    ).fetchone()
    if exists:
        return

    conn.execute(
        """INSERT INTO spell
             (person_id, position_id, start_date, start_precision,
              end_date, end_precision, confidence)
           VALUES (?, ?, ?, ?, ?, ?, 1.0)""",
        (person_id, position_id, start, start_prec, end, end_prec),
    )
    report.spells_created += 1
