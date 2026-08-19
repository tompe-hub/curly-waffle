# cadre-watch

A daily monitor for CCP personnel transitions — purges, promotions, retirements —
that surfaces what changed on a dashboard rather than pushing alerts.

**Status: v0.1.** Three sources implemented (CCDI discipline-inspection
announcements, NPC Standing Committee 任免 decisions, State Council personnel
notices), extraction is rule-based with no LLM in the loop, and the dashboard
has its four views. See [Scope](#what-v0-does-and-does-not-do).

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

## Getting to the dashboard

**There is no hosted instance and no URL.** This is a local application: the
dashboard is a small web server you run on your own machine, reading a SQLite
file the daily job writes next to it. Nothing is deployed anywhere.

Needs Python 3.11 or newer. From a clean checkout:

```bash
git clone -b claude/personnel-website-monitor-1p7o7r \
    https://github.com/tompe-hub/curly-waffle.git cadre-watch
cd cadre-watch

python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/cadre init                    # create the database, seed the watchlist
CADRE_OFFLINE=1 .venv/bin/cadre run     # populate it from the test fixtures
.venv/bin/cadre serve                   # serves on http://127.0.0.1:8000
```

Then open <http://127.0.0.1:8000> in a browser on that same machine. Ctrl-C
stops it. Drop `CADRE_OFFLINE=1` to fetch the real sites instead of fixtures —
but read [Before your first live run](#before-your-first-live-run) first, and
expect an empty dashboard until the selectors are verified.

The dashboard shows whatever is in the database; it does not fetch anything
itself. If it looks empty, run `cadre run`, then `cadre stats` to confirm rows
exist.

### Reaching it on a server

**The dashboard has no authentication.** Anyone who can reach the port can read
everything and click the review buttons. So when it runs on a VPS, leave it
bound to localhost and tunnel in over SSH rather than exposing it:

```bash
# on the server, from cron or a systemd unit
cadre serve --host 127.0.0.1 --port 8000

# from your laptop
ssh -N -L 8000:127.0.0.1:8000 you@your-server
```

Then open <http://127.0.0.1:8000> locally. Do not pass `--host 0.0.0.0` unless
you have put a reverse proxy with authentication in front of it.

Against the live site, drop `CADRE_OFFLINE` — but read
[Before your first live run](#before-your-first-live-run) first.

```bash
.venv/bin/python -m pytest              # 39 tests, no network needed
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

**Two extraction grammars, because the sources have two.** Discipline-inspection
notices are about one person whose name sits at the end of a title, so they use
phrase matching plus a backward surname scan, with a document-level subject
carried into later clauses that say only 其 ("his/her"). 任免 decisions name
dozens of people in bracketed constructions — `免去 X 的 Y 职务`, `任命 X 为 Y` —
so the name is captured by the grammar rather than guessed, and one document
yields one signal per person.

**Punitive and neutral verbs stay distinct.** `撤销职务` and `罢免` are
disciplinary acts. `免去` is the routine word and covers promotion, retirement
and purge alike. Collapsing them into "removed" would discard the only
information 任免 text carries without a classifier.

**A departure with an onward post is a reshuffle.** When a document removes
someone and appoints them to something else, that pairing is detected and the
removal is discounted in ranking. A removal with nothing following it stays at
full weight — that is the case worth looking at, and it is the single most
useful discriminator available in appointment data before the classifier
exists.

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

1. **Every source's URLs and selectors are unverified.** They were written from
   the shapes these CMS pages have historically used, but development happened
   in a sandbox whose network policy blocks all three hosts, so no live fetch
   ever confirmed them. Run the diagnostic first, once per source:

   ```bash
   .venv/bin/cadre check-source ccdi
   .venv/bin/cadre check-source npc
   .venv/bin/cadre check-source state_council
   ```

   It reports what each listing selector matched with sample links, then fetches
   one real article and checks the body extraction separately — the two break
   independently. **When a selector finds nothing it does not just say so:** it
   reads the HTML that came back, ranks the elements that actually contain
   article links (and, for bodies, the densest block of Chinese text), and
   prints the selectors that would work. Paste them into `LIST_CONTAINERS` /
   `BODY_SELECTORS` / `LISTINGS` on the source class and re-run. Exit status is
   non-zero when anything is wrong, so it drops straight into a smoke test.

   Site redesigns are the expected long-run failure mode of this whole system,
   so this diagnostic is the tool you will reach for most.

2. **Check network reachability from wherever you host.** Chinese government
   sites are generally reachable from Europe and the US, but some rate-limit or
   geo-block foreign IPs. This is the main unknown in the whole project, so test
   it before committing to a design. If you hit walls, a Hong Kong or Singapore
   egress proxy is the usual fix.

## What v0 does and does not do

**Implemented:** three sources on a shared CMS base; a phrase lexicon covering
the discipline-inspection pipeline (investigation → surrender → detention →
expulsion → prosecution → sentencing); a pattern lexicon covering 任免
(appointment, removal, dismissal, recall, resignation) with reshuffle detection;
entity resolution with a review queue; significance ranking; event clustering;
the archive; selector autodiscovery; and a four-view dashboard.

**Not yet, in build order:**

1. **A real watchlist.** `seed/watchlist.csv` is fourteen people for smoke
   testing, not a dataset. Bootstrap properly from CPED (Chinese Political Elite
   Database) or Wikidata rather than scraping career histories yourself.
2. **Roster snapshotting and scrub detection** — diff official leadership pages,
   with a run-level sanity floor so a failed scrape never reads as mass removal.
3. **Appearance ingestion and the quiet list** — the highest-value view, and the
   long pole: it needs 12–24 months of history loaded before an absence means
   anything, so start collecting early even though the view ships late. Needs a
   blackout calendar (Beidaihe every August, Spring Festival, National Day) or
   it fires on the entire leadership each summer.
4. **The transition classifier** — rules first, emitting a distribution over
   {promotion, lateral, retirement, sidelined, purge, death} plus evidence,
   never a bare label. Watch for the "kicked upstairs" case: a move to an NPC or
   CPPCC committee seat scores as a promotion by rank and is career termination
   in fact.
5. **LLM extraction pass** on the tail the rules miss, via the Batch API (50%
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
  sources/          base.py (fetcher + selector discovery), cms.py (shared
                    CMS parsing), ccdi.py, npc.py, statecouncil.py
  extract/          lexicon.py (phrases, patterns, glosses), rules.py
  resolve.py        name → person, with an explicit ambiguous outcome
  cluster.py        signals → events
  score.py          significance ranking
  pipeline.py       the daily job; idempotent, replayable
  web/              FastAPI dashboard + templates
  cli.py            init / run / reextract / check-source / serve / stats
seed/watchlist.csv  starter watchlist (replace with a CPED import)
tests/              39 tests, fixture-driven, no network
```
