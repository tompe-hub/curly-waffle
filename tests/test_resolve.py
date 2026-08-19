from __future__ import annotations

from cadre.resolve import known_names, resolve_name


def test_unique_name_resolves(conn):
    res = resolve_name(conn, "唐仁健", "农业农村部党组书记")
    assert res.status == "resolved"
    assert res.person_id is not None


def test_unknown_name_goes_to_the_queue(conn):
    res = resolve_name(conn, "张伟", "江南省人民政府原副省长")
    assert res.status == "unknown_person"
    assert res.person_id is None


def test_homonyms_are_ambiguous_not_guessed(conn):
    """Two people share a name -- the system must refuse to pick one."""
    conn.execute("INSERT INTO person (name_zh) VALUES ('王伟')")
    conn.execute("INSERT INTO person (name_zh) VALUES ('王伟')")
    conn.commit()
    res = resolve_name(conn, "王伟", "某部副部长")
    assert res.status == "ambiguous"
    assert res.person_id is None
    assert len(res.candidates) == 2


def test_known_names_covers_everyone_not_just_the_watchlist(conn):
    conn.execute("INSERT INTO person (name_zh) VALUES ('不在名单者')")
    conn.commit()
    assert "不在名单者" in known_names(conn)
    assert "唐仁健" in known_names(conn)
