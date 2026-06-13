# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A daily tech-news tracker with a Flask web dashboard, focused on **AI** and
**Quantum**, with emphasis on **Chinese tech**. It aggregates curated RSS feeds,
keyword-tags each article (`ai` / `quantum` / `china`), stores them in SQLite,
and serves a filterable dashboard.

## Commands

All commands assume the virtualenv is active (`source .venv/bin/activate`).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m tracker.fetch         # fetch all feeds, classify, store into data.db
python -m tracker.web           # serve dashboard at http://127.0.0.1:5000
python -m tracker.sample_data   # seed sample articles (offline/dev, no network)
```

There is no test suite yet. The fastest end-to-end check is the in-process
Flask test client:

```bash
python -c "from tracker.web import app; print(app.test_client().get('/').status_code)"
```

## Architecture

The data flow is **feeds → fetch/classify → SQLite → web**, with each stage in
its own module under `tracker/`:

- **`feeds.py`** — loads and validates the source list from `config/feeds.json`
  into `Feed` objects. Sources live in JSON (not code) so the feed list is
  editable without touching Python. Each feed carries a `region`
  (`china`/`global`) and optional forced `tags`.
- **`classify.py`** — transparent keyword matching. Tags an article `ai`/`quantum`
  by keywords in title+summary, and `china` if it's from a China-region feed
  *or* mentions China-related keywords (companies, places, labs). Tune behavior
  by editing the keyword lists at the top of this file.
- **`store.py`** — SQLite layer. Single `articles` table keyed by a hash of the
  link, so re-fetching is an idempotent `INSERT OR IGNORE`. Tags are stored as a
  comma-separated string; tag filtering uses a `LIKE '%,tag,%'` match. `data.db`
  is gitignored (local cache).
- **`fetch.py`** — orchestrates a refresh: downloads each feed via `requests`
  (so HTTP/egress errors are explicit, not feedparser's opaque "syntax error"),
  parses with `feedparser`, classifies, and upserts. One failing feed never
  breaks the run; `refresh()` returns a summary with per-feed failure reasons.
- **`web.py`** — Flask app. `GET /` renders the dashboard with `tag`, `region`,
  and `days` query-param filters; `POST /refresh` triggers a synchronous fetch
  and redirects back, preserving filters. Templates in `templates/`, CSS in
  `static/`.

## Network egress constraint (important)

This repo is typically run in a remote environment with a **network egress
allowlist**. Live feed hosts (arxiv.org, technode.com, hnrss.org, etc.) are
usually **not** on it, so `python -m tracker.fetch` will report every feed as
`blocked by network egress allowlist` and store nothing. This is an environment
restriction, not a code bug. To work on the dashboard without network access,
seed with `python -m tracker.sample_data`. To fetch live feeds, the feed hosts
must be added to the environment's egress allowlist.

## Conventions

- Sources are data, not code — add/remove feeds in `config/feeds.json`.
- Keep classification keyword-based and explainable; extend the lists in
  `classify.py` rather than adding opaque heuristics.
- The default branch is `main`. Do not create a pull request unless explicitly asked.
