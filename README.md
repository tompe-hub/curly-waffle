# cadre-watch

A daily monitor for CCP personnel transitions — purges, promotions, retirements —
that surfaces what changed on a dashboard rather than pushing alerts.

**Status: v0.** One source is implemented for real (CCDI discipline-inspection
announcements), extraction is rule-based with no LLM in the loop, and the
dashboard has its two core views. See [Scope](#what-v0-does-and-does-not-do).

---

## The idea in one paragraph

Nobody publishes "X was purged." They publish a removal decision with no reason,
and months later a discipline-inspection notice, and you infer backwards. So the
system separates **position-holding facts** (who holds what, over what period)
from **transition events** (a holding ended) from **classification** (why it
ended) from **confidence** (how sure we are). Most of the engineering is in the
first; most of the value is in the last two. Everything the system claims points
at an archived document and a verbatim Chinese span, because a research tool
that cannot show its work is not usable.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/cadre init                    # create the database, seed the watchlist
CADRE_OFFLINE=1 .venv/bin/cadre run     # run against the test fixtures
.venv/bin/cadre serve                   # dashboard on http://127.0.0.1:8000
```

Against the live site, drop `CADRE_OFFLINE` — but read
[Before your first live run](#before-your-first-live-run) first.

```bash
.venv/bin/python -m pytest              # 29 tests, no network needed
```

### Daily, from cron

```cron
0 2 * * *  cd /srv/cadre && CADRE_DATA=/srv/cadre/data .venv/bin/cadre run >> /var/log/cadre.log 2>&1
```

02:00 Beijing time is after the previous day's news cycle has settled, including
the Friday-evening announcement dumps. The job is idempotent — running it twice
costs a few HTTP requests and changes nothing — so a retry is always safe.

## How it works

```
fetch → archive → extract → resolve → score → cluster → dashboard
```

| Stage | Module | What it does |
|---|---|---|
| fetch | `cadre/sources/` | Polite, sequential, rate-limited. Offline fixture mode for tests. |
| archive | `cadre/archive.py` | Content-addressed gzip of every document, hashed on extracted text. |
| extract | `cadre/extract/` | Curated phrase lexicon → signals, with verbatim spans. |
| resolve | `cadre/resolve.py` | Name → person. Resolved / ambiguous / unknown. |
| score | `cadre/score.py` | Significance ranking — no thresholds, only an order. |
| cluster | `cadre/cluster.py` | Many signals → one event, so one purge is one row. |
| dashboard | `cadre/web/` | What's new, person pages, review queue, run health. |

### Design decisions worth knowing

**Spells, not current state.** A person holds several positions concurrently
(party post, state post, commissions), and losing one while keeping another is
itself a signal. Date precision is a column, because "sometime in Q3 2025" is a
common and real answer.

**The archive is the source of truth; the database is derived.** Fix a rule, run
`cadre reextract`, and history is replayed. This is also the only foundation on
which scrub detection can later work.

**Rules before models.** These announcements are formulaic — `涉嫌严重违纪违法，
目前正接受中央纪委国家监委纪律审查和监察调查` is near-boilerplate. Matching that
deterministically is cheap, fast, and *auditable*: every claim traces to a
phrase id in `cadre/extract/lexicon.py`. An LLM pass belongs on the tail that
rules cannot resolve, not on the formulaic core.

**English glosses are fixed, not machine-translated.** The exact phrase drives
the classification, so its rendering must not drift. Each `Phrase` carries its
own gloss.

**Uncertainty is surfaced, never hidden.** A name that could be two people
becomes a review-queue item, not a coin flip. A surname-guessed name is flagged
as a guess and discounted in ranking — once, in scoring; extraction confidence
measures only the phrase match. (Applying both discounts to one number, as an
earlier draft did, sank an unidentified official's fresh investigation below
routine follow-up on a known one — exactly backwards for a tool whose edge is
coverage depth.)

**No thresholds.** Because this is a dashboard and not a pager, the absence and
significance logic can rank rather than decide. That removes the hardest
calibration problem in the whole design.

**Empty is not the same as quiet.** A source that returned links before and now
returns none is flagged `empty` on the Runs page. A site redesign is far more
likely than a silent week, and reporting "nothing happened" would be a lie.

## Before your first live run

Two things need your attention, and both are honest gaps rather than oversights:

1. **The CCDI selectors are unverified.** They were written from the shapes these
   CMS pages have historically used, but development happened in a sandbox whose
   network policy blocks `ccdi.gov.cn`, so no live fetch ever confirmed them.
   Run the diagnostic first:

   ```bash
   .venv/bin/cadre check-source ccdi
   ```

   It reports what each listing selector matched, with sample links. If it finds
   nothing, fix `LISTINGS` / `_LIST_CONTAINERS` / `_BODY_SELECTORS` in
   `cadre/sources/ccdi.py` — they are all in one place at the top of the file.

2. **Check network reachability from wherever you host.** Chinese government
   sites are generally reachable from Europe and the US, but some rate-limit or
   geo-block foreign IPs. This is the main unknown in the whole project, so test
   it before committing to a design. If you hit walls, a Hong Kong or Singapore
   egress proxy is the usual fix.

## What v0 does and does not do

**Implemented:** CCDI source, phrase lexicon covering the discipline-inspection
pipeline (investigation → surrender → detention → expulsion → prosecution →
sentencing), entity resolution with a review queue, significance ranking, event
clustering, the archive, and a four-view dashboard.

**Not yet, in build order:**

1. **NPC and State Council 任免 notices** — stubs at `cadre/sources/stubs.py`,
   same interface. Needs the appointment/removal lexicon, a different vocabulary
   from discipline inspection.
2. **A real watchlist.** `seed/watchlist.csv` is fourteen people for smoke
   testing, not a dataset. Bootstrap properly from CPED (Chinese Political Elite
   Database) or Wikidata rather than scraping career histories yourself.
3. **Roster snapshotting and scrub detection** — diff official leadership pages,
   with a run-level sanity floor so a failed scrape never reads as mass removal.
4. **Appearance ingestion and the quiet list** — the highest-value view, and the
   long pole: it needs 12–24 months of history loaded before an absence means
   anything, so start collecting early even though the view ships late. Needs a
   blackout calendar (Beidaihe every August, Spring Festival, National Day) or
   it fires on the entire leadership each summer.
5. **The transition classifier** — rules first, emitting a distribution over
   {promotion, lateral, retirement, sidelined, purge, death} plus evidence,
   never a bare label. Watch for the "kicked upstairs" case: a move to an NPC or
   CPPCC committee seat scores as a promotion by rank and is career termination
   in fact.
6. **LLM extraction pass** on the tail the rules miss, via the Batch API (50%
   off, and a daily job has no latency requirement).

## Costs

A small VPS (~$5–9/mo), a few GB of storage a year, and $0 in inference while
extraction stays rule-based. Adding the LLM tail pass with rules-first filtering
and batch pricing lands around $60/mo; a 24-month historical backfill is a
one-time charge in the high hundreds to low thousands depending on model choice
and scope.

## Legal and ethical notes

Names and job titles are personal data under GDPR/UK GDPR and CCPA even when
published publicly, and this system stores profiles over time. If you operate in
or serve those jurisdictions you have controller obligations — lawful basis,
retention limits, subject access. Research and journalism carve-outs may apply;
they are not automatic.

Fetch politely: the default is sequential with a 2-second delay per request, and
`cadre run` respects it. Do not raise it because a run feels slow. Stick to
public official sources; do not point this at LinkedIn, whose terms prohibit it.

## Layout

```
cadre/
  schema.sql        the data model, commented
  config.py         env-driven configuration
  db.py             connection + idempotent migration
  archive.py        content-addressed document store
  sources/          base interface, fetcher, CCDI, stubs
  extract/          lexicon.py (phrases + glosses), rules.py (matching)
  resolve.py        name → person, with an explicit ambiguous outcome
  cluster.py        signals → events
  score.py          significance ranking
  pipeline.py       the daily job; idempotent, replayable
  web/              FastAPI dashboard + templates
  cli.py            init / run / reextract / check-source / serve / stats
seed/watchlist.csv  starter watchlist (replace with a CPED import)
tests/              29 tests, fixture-driven, no network
```
