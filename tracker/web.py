"""Flask dashboard for the daily tracker.

Routes
------
GET  /            Daily dashboard (filterable by tag, region, day count).
POST /refresh     Trigger a synchronous feed refresh, then redirect home.

Run with::

    python -m tracker.web      # or: flask --app tracker.web run
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Flask, redirect, render_template, request, url_for

from . import fetch
from .store import query_articles, tag_counts

app = Flask(__name__, template_folder="../templates", static_folder="../static")

VALID_TAGS = {"ai", "quantum", "china"}
VALID_REGIONS = {"china", "global"}


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@app.route("/")
def index():
    tag = request.args.get("tag") or None
    region = request.args.get("region") or None
    days = request.args.get("days", default=1, type=int)
    days = max(1, min(days, 30))

    if tag not in VALID_TAGS:
        tag = None
    if region not in VALID_REGIONS:
        region = None

    since = _since(days)
    articles = query_articles(tag=tag, region=region, since=since, limit=300)
    counts = tag_counts(since=since)

    return render_template(
        "index.html",
        articles=articles,
        counts=counts,
        active_tag=tag,
        active_region=region,
        days=days,
        now=datetime.now(timezone.utc),
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    fetch.refresh()
    # Preserve current filters across the redirect.
    return redirect(url_for("index", **{k: v for k, v in request.args.items()}))


def main() -> None:
    app.run(host="127.0.0.1", port=5000, debug=True)


if __name__ == "__main__":
    main()
