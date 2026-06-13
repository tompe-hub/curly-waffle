# curly-waffle

A daily tech-news tracker with a web dashboard, focused on **AI** and **Quantum**,
with special emphasis on **Chinese tech**. It aggregates curated RSS feeds, tags
each article (`ai` / `quantum` / `china`), stores them in SQLite, and serves a
filterable daily dashboard.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m tracker.fetch      # pull the latest articles into data.db
python -m tracker.web        # serve the dashboard at http://127.0.0.1:5000
```

The dashboard also has a **Refresh feeds** button that fetches on demand, so the
separate `tracker.fetch` step is optional for casual use — it's mainly there for
scheduling (e.g. a daily cron job).

## What it does

- **Sources** — curated RSS/Atom feeds defined in [`config/feeds.json`](config/feeds.json).
  Each feed is marked `china` or `global`. Add or remove feeds by editing that
  file; no code changes needed.
- **Tagging** — simple, transparent keyword matching ([`tracker/classify.py`](tracker/classify.py))
  tags articles `ai`, `quantum`, and/or `china`. China-region feeds are always
  tagged `china`; global feeds get the `china` tag when their text mentions
  Chinese tech (companies, places, labs).
- **Dashboard** — filter by topic (AI / Quantum / China), by region
  (China / Global), and by time window (1 / 3 / 7 days).

## Daily automation

To refresh every morning, schedule the fetch step (it's network-only and writes
to `data.db`):

```cron
0 8 * * *  cd /path/to/curly-waffle && .venv/bin/python -m tracker.fetch
```

## Tuning

- **Add a source:** add an entry to `config/feeds.json`.
- **Change what counts as AI / Quantum / China:** edit the keyword lists in
  `tracker/classify.py`.
