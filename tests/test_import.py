"""Roster import.

The failure this design is built around is a silently mis-mapped column, so the
tests care as much about what the importer refuses to guess as about what it
loads."""
from __future__ import annotations

from pathlib import Path

import pytest

from cadre.importers import import_roster, inspect_file, resolve_mapping
from cadre.importers.ranks import is_sideline, rank_score, tier_for
from cadre.importers.roster import parse_date

FIXTURES = Path(__file__).parent / "fixtures"
CPED = FIXTURES / "roster_cped_sample.csv"
WIKIDATA = FIXTURES / "roster_wikidata_sample.csv"
ODD = FIXTURES / "roster_odd_headers.csv"


# ------------------------------------------------------------- mapping ------

def test_cped_style_headers_resolve():
    mapping, _, _ = inspect_file(CPED)
    assert mapping.ok and mapping.has_spells
    assert mapping.resolved["name_zh"] == "name_zh"
    assert mapping.resolved["rank"] == "admin_rank"
    assert mapping.resolved["org"] == "work_unit"
    assert mapping.resolved["external_id"] == "person_id"


def test_wikidata_style_headers_resolve_the_same_fields():
    """A different dataset's spelling of the same concepts must land in the
    same fields -- that is the point of alias matching over a fixed schema."""
    mapping, _, _ = inspect_file(WIKIDATA)
    assert mapping.ok
    assert mapping.resolved["name_zh"] == "personLabel"
    assert mapping.resolved["external_id"] == "person"
    assert mapping.resolved["position_title"] == "positionLabel"


def test_unrecognised_headers_abort_rather_than_guess():
    mapping, _, _ = inspect_file(ODD)
    assert not mapping.ok
    assert "name_zh" in mapping.unmatched_fields


def test_near_miss_headers_get_a_suggestion():
    mapping, _, _ = inspect_file(ODD)
    assert mapping.suggestions.get("name_zh") == "name_zh_full"


def test_explicit_override_wins():
    mapping, _, _ = inspect_file(ODD, {"name_zh": "name_zh_full"})
    assert mapping.ok
    assert mapping.resolved["name_zh"] == "name_zh_full"


def test_override_of_an_unknown_field_is_rejected():
    with pytest.raises(ValueError, match="unknown field"):
        resolve_mapping(["a"], {"nonsense": "a"})


# ------------------------------------------------------- rank and tier ------

@pytest.mark.parametrize("raw,expected", [
    ("正部级", 80), ("省部级正职", 80), ("部级", 80),
    ("副部级", 70), ("省部级副职", 70),      # must not match the shorter 部级
    ("ministerial", 80), ("vice-ministerial", 70),
    ("正国级", 100), ("厅局级正职", 60),
    ("", None), ("gibberish", None),
])
def test_rank_scores_resolve_most_specific_first(raw, expected):
    assert rank_score(raw) == expected


@pytest.mark.parametrize("cc,rank,expected", [
    ("中央政治局常委", "正国级", 1),
    ("中央委员", "正部级", 2),
    ("候补中央委员", "正部级", 3),
    (None, "正部级", 3),
    (None, "副部级", 4),
    # committee standing and rank are independent readings of seniority, and
    # the more senior one wins: an NPC vice-chairman is 副国级 and outranks an
    # ordinary Central Committee member
    ("中央委员", "副国级", 1),
    ("中央政治局委员", None, 1),
    (None, None, 4),
])
def test_tier_takes_the_more_senior_of_committee_and_rank(cc, rank, expected):
    assert tier_for(cc_status=cc, rank=rank) == expected


@pytest.mark.parametrize("title,expected", [
    ("全国人民代表大会常务委员会副委员长", True),
    ("中国人民政治协商会议全国委员会副主席", True),
    ("一级巡视员", True),
    ("农业农村部部长", False),
    ("外交部部长", False),
])
def test_sideline_posts_are_recognised(title, expected):
    assert is_sideline(title) is expected


# --------------------------------------------------------------- dates ------

@pytest.mark.parametrize("raw,expected", [
    ("2020-12-05", ("2020-12-05", "day")),
    ("2020-12", ("2020-12-01", "month")),
    ("2020", ("2020-01-01", "year")),
    ("2020年3月", ("2020-03-01", "month")),
    ("", (None, None)),
    ("NA", (None, None)),
])
def test_date_precision_is_recorded_not_invented(raw, expected):
    assert parse_date(raw) == expected


# --------------------------------------------------------------- import -----

def test_import_loads_people_spells_orgs_and_positions(conn):
    report = import_roster(conn, CPED, max_tier=3)
    assert report.people_created == 5      # 唐仁健 appears twice, one person
    assert report.spells_created == 6
    assert report.orgs_created == 6

    row = conn.execute(
        "SELECT * FROM person WHERE name_zh = '唐仁健' AND source_dataset = 'cped'"
    ).fetchone()
    assert row["birth_year"] == 1962
    assert row["native_place"] == "重庆"
    spells = conn.execute(
        "SELECT COUNT(*) FROM spell WHERE person_id = ?", (row["id"],)
    ).fetchone()[0]
    assert spells == 2


def test_tier_is_the_most_senior_standing_seen(conn):
    import_roster(conn, CPED, max_tier=4)
    tiers = {
        r["name_zh"]: r["tier"] for r in conn.execute(
            """SELECT p.name_zh, w.tier FROM watchlist w
                 JOIN person p ON p.id = w.person_id
                WHERE p.source_dataset = 'cped'"""
        )
    }
    assert tiers["李强"] == 1          # Politburo Standing Committee
    assert tiers["王守成"] == 1        # 副国级 outranks his CC membership
    assert tiers["唐仁健"] == 2        # Central Committee full member
    assert tiers["陈建国"] == 4        # 副部级, no CC standing


def test_max_tier_filters_the_watchlist_but_not_the_people(conn):
    """Everyone becomes a person so extraction can recognise their name; the
    watchlist is the narrower set."""
    import_roster(conn, CPED, max_tier=2)
    people = conn.execute(
        "SELECT COUNT(*) FROM person WHERE source_dataset = 'cped'").fetchone()[0]
    watched = conn.execute(
        """SELECT COUNT(*) FROM watchlist w JOIN person p ON p.id = w.person_id
            WHERE p.source_dataset = 'cped'""").fetchone()[0]
    assert people == 5
    # 李强 and 王守成 at tier 1; 唐仁健 and 秦刚 at tier 2. 陈建国 (tier 4) is
    # imported as a person but not watched.
    assert watched == 4


def test_sideline_posts_are_flagged(conn):
    """An NPC Standing Committee seat reads as senior by rank and is career
    termination in fact -- a rank-delta classifier needs this flag or it scores
    the move as a promotion."""
    import_roster(conn, CPED)
    row = conn.execute(
        """SELECT pos.is_sideline FROM position pos JOIN org o ON o.id = pos.org_id
            WHERE o.name_zh = '全国人民代表大会常务委员会'"""
    ).fetchone()
    assert row["is_sideline"] == 1

    ordinary = conn.execute(
        """SELECT pos.is_sideline FROM position pos JOIN org o ON o.id = pos.org_id
            WHERE o.name_zh = '农业农村部'"""
    ).fetchone()
    assert ordinary["is_sideline"] == 0


def test_rank_scores_are_stored_for_later_comparison(conn):
    import_roster(conn, CPED)
    scores = {
        r["title_zh"]: r["rank_score"]
        for r in conn.execute("SELECT title_zh, rank_score FROM position")
    }
    assert scores["总理"] == 100        # 正国级
    assert scores["部长"] == 80         # 正部级
    assert scores["副部长"] == 70       # 副部级 -- not 80


def test_reimport_is_idempotent(conn):
    import_roster(conn, CPED)
    counts = lambda: tuple(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                           for t in ("person", "spell", "org", "position", "watchlist"))
    before = counts()
    second = import_roster(conn, CPED)
    assert counts() == before
    assert second.people_created == 0
    assert second.spells_created == 0


def test_dry_run_writes_nothing(conn):
    before = conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    report = import_roster(conn, CPED, dry_run=True)
    assert report.people_created == 5          # it reports what it would do
    assert conn.execute("SELECT COUNT(*) FROM person").fetchone()[0] == before


def test_a_later_blank_does_not_erase_an_earlier_value(conn, tmp_path):
    """Row two of a person's spells often omits the bio columns. Filling gaps
    is right; overwriting with blanks is not."""
    path = tmp_path / "gaps.csv"
    path.write_text(
        "person_id,name_zh,birth_year,native_place,position\n"
        "X1,测试人,1970,福建,部长\n"
        "X1,测试人,,,副部长\n",
        encoding="utf-8",
    )
    import_roster(conn, path, dataset="test")
    row = conn.execute("SELECT * FROM person WHERE name_zh = '测试人'").fetchone()
    assert row["birth_year"] == 1970
    assert row["native_place"] == "福建"


def test_imported_names_become_resolvable_in_extraction(conn):
    """The point of importing everyone, not just the watchlist: a name we know
    turns an unresolved review-queue item into a resolved signal."""
    from cadre.resolve import known_names, resolve_name
    import_roster(conn, CPED, max_tier=2)
    assert "陈建国" in known_names(conn)          # tier 4, not watchlisted
    assert resolve_name(conn, "陈建国", "水利部副部长").status == "resolved"


def test_stata_files_are_refused_with_the_conversion_command(conn, tmp_path):
    path = tmp_path / "cped.dta"
    path.write_bytes(b"not really stata")
    with pytest.raises(ValueError, match="pyreadstat"):
        import_roster(conn, path)
