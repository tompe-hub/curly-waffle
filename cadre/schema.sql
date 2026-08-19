-- cadre-watch schema (v0)
--
-- Design notes:
--   * Spells, not current state. A person holds many positions concurrently and
--     we care about when each holding started and ended.
--   * Date precision is a first-class field. "Sometime in Q3 2025" is a real,
--     common answer and forcing it into a DATE destroys information.
--   * Every claim points at a document, and every document is archived on disk.
--     We re-extract history whenever the extractor improves.
--   * signal = one claim from one document.  event = one real-world happening,
--     to which many signals attach as corroboration.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- people ----

CREATE TABLE IF NOT EXISTS person (
    id            INTEGER PRIMARY KEY,
    name_zh       TEXT NOT NULL,
    name_pinyin   TEXT,
    birth_year    INTEGER,
    birth_month   INTEGER,
    sex           TEXT,
    native_place  TEXT,          -- 籍贯, key disambiguator for common names
    ethnicity     TEXT,
    notes         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_person_name ON person(name_zh);

-- Watchlist tier drives significance scoring. 1 = Politburo and above,
-- 2 = Central Committee full member, 3 = alternate / full-ministerial,
-- 4 = vice-ministerial and below.
CREATE TABLE IF NOT EXISTS watchlist (
    person_id  INTEGER PRIMARY KEY REFERENCES person(id) ON DELETE CASCADE,
    tier       INTEGER NOT NULL DEFAULT 3,
    added_at   TEXT NOT NULL DEFAULT (datetime('now')),
    note       TEXT
);

-- ------------------------------------------------------- orgs & positions ---

CREATE TABLE IF NOT EXISTS org (
    id           INTEGER PRIMARY KEY,
    name_zh      TEXT NOT NULL UNIQUE,
    name_en      TEXT,
    kind         TEXT,           -- party | state | military | provincial | soe
    parent_id    INTEGER REFERENCES org(id),
    jurisdiction TEXT
);

-- rank_score makes ranks comparable: promotion is a rank_score increase.
-- is_sideline marks the "kicked upstairs" destinations (NPC/CPPCC committee
-- seats, 巡视员) that look lateral by rank but are career termination.
CREATE TABLE IF NOT EXISTS position (
    id          INTEGER PRIMARY KEY,
    org_id      INTEGER REFERENCES org(id),
    title_zh    TEXT NOT NULL,
    title_en    TEXT,
    admin_rank  TEXT,
    rank_score  INTEGER,
    prestige    INTEGER DEFAULT 0,  -- hand-curated; Guangdong > Qinghai at equal rank
    is_sideline INTEGER NOT NULL DEFAULT 0,
    UNIQUE(org_id, title_zh)
);

CREATE TABLE IF NOT EXISTS spell (
    id              INTEGER PRIMARY KEY,
    person_id       INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    position_id     INTEGER NOT NULL REFERENCES position(id),
    start_date      TEXT,
    start_precision TEXT,        -- day | month | year | unknown
    end_date        TEXT,
    end_precision   TEXT,
    end_type        TEXT,        -- promotion|lateral|retirement|purge|death|sidelined|unknown
    confidence      REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_spell_person ON spell(person_id);

-- ------------------------------------------------------------ documents ----

-- sha256 is over the extracted text, not the raw bytes: gov sites churn
-- session ids and timestamps in markup, which would defeat dedup on raw HTML.
CREATE TABLE IF NOT EXISTS document (
    id                INTEGER PRIMARY KEY,
    sha256            TEXT NOT NULL UNIQUE,
    source_id         TEXT NOT NULL,
    url               TEXT NOT NULL,
    title             TEXT,
    published_at      TEXT,
    fetched_at        TEXT NOT NULL,
    archive_path      TEXT NOT NULL,
    text_len          INTEGER,
    extracted_at      TEXT,
    extractor_version TEXT
);
CREATE INDEX IF NOT EXISTS idx_document_source ON document(source_id, published_at);
CREATE INDEX IF NOT EXISTS idx_document_extracted ON document(extracted_at);

-- ----------------------------------------------------------------- runs ----

CREATE TABLE IF NOT EXISTS run (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running',  -- running|ok|partial|failed
    stats_json  TEXT
);

CREATE TABLE IF NOT EXISTS run_source (
    id         INTEGER PRIMARY KEY,
    run_id     INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    source_id  TEXT NOT NULL,
    status     TEXT NOT NULL,       -- ok | empty | error
    docs_seen  INTEGER DEFAULT 0,
    docs_new   INTEGER DEFAULT 0,
    error      TEXT
);

-- --------------------------------------------------- signals and events ----

CREATE TABLE IF NOT EXISTS event (
    id            INTEGER PRIMARY KEY,
    person_id     INTEGER REFERENCES person(id) ON DELETE CASCADE,
    raw_name      TEXT,              -- set when person_id is NULL (unresolved)
    kind          TEXT NOT NULL,
    event_date    TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    significance  REAL NOT NULL DEFAULT 0,
    review_state  TEXT NOT NULL DEFAULT 'new',  -- new|seen|confirmed|dismissed|watching
    reviewed_at   TEXT,
    summary       TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_state ON event(review_state, significance DESC);
CREATE INDEX IF NOT EXISTS idx_event_person ON event(person_id);

CREATE TABLE IF NOT EXISTS signal (
    id            INTEGER PRIMARY KEY,
    document_id   INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    run_id        INTEGER REFERENCES run(id),
    event_id      INTEGER REFERENCES event(id) ON DELETE SET NULL,
    kind          TEXT NOT NULL,
    person_id     INTEGER REFERENCES person(id),
    raw_name      TEXT,
    raw_position  TEXT,
    quoted_span   TEXT NOT NULL,     -- verbatim Chinese; the audit trail
    event_date    TEXT,
    rule_id       TEXT NOT NULL,
    confidence    REAL NOT NULL DEFAULT 0,
    resolution    TEXT NOT NULL,     -- resolved | ambiguous | unknown_person
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(document_id, kind, raw_name)
);
CREATE INDEX IF NOT EXISTS idx_signal_resolution ON signal(resolution);
CREATE INDEX IF NOT EXISTS idx_signal_event ON signal(event_id);

-- Candidate matches for signals we could not resolve to exactly one person.
CREATE TABLE IF NOT EXISTS resolution_candidate (
    id        INTEGER PRIMARY KEY,
    signal_id INTEGER NOT NULL REFERENCES signal(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    score     REAL NOT NULL,
    method    TEXT NOT NULL
);

-- "Since you last looked" boundary for the dashboard.
CREATE TABLE IF NOT EXISTS visit (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL DEFAULT (datetime('now'))
);
