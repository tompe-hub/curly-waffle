"""Seed the database with sample articles.

Useful for trying out the dashboard offline or in restricted-network
environments where live feeds aren't reachable::

    python -m tracker.sample_data
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .classify import classify
from .store import Article, upsert_articles

_SAMPLES = [
    ("Pandaily", "china", "DeepSeek releases new open-weight reasoning model",
     "The Chinese AI lab DeepSeek published a large language model it says rivals leading systems on math and coding benchmarks."),
    ("TechNode", "china", "Huawei unveils domestic AI accelerator for data centers",
     "Huawei detailed a new Ascend-series chip aimed at training large neural networks without foreign hardware."),
    ("SCMP Tech", "china", "Chinese researchers report quantum computing milestone",
     "A team in Hefei demonstrated a photonic quantum processor they claim shows quantum advantage on a sampling task."),
    ("The Quantum Insider", "global", "IBM expands superconducting qubit roadmap",
     "IBM outlined plans to scale its quantum systems past 1,000 qubits with new error-correction techniques."),
    ("MIT Technology Review", "global", "What the latest LLM agents can and can't do",
     "A look at how agentic AI systems are being deployed, and where they still fall short on reliability."),
    ("Ars Technica", "global", "Alibaba Cloud open-sources a multimodal model",
     "The Chinese cloud giant released a vision-language model under a permissive license, intensifying competition with Western labs."),
    ("VentureBeat AI", "global", "Startups race to build inference chips",
     "A wave of companies is targeting cheaper AI inference, including several backed by Chinese investors."),
]


def seed() -> int:
    now = datetime.now(timezone.utc)
    articles = []
    for i, (source, region, title, summary) in enumerate(_SAMPLES):
        published = (now - timedelta(hours=i * 5)).isoformat()
        tags = classify(title, summary, region)
        articles.append(
            Article(
                source=source,
                region=region,
                title=title,
                link=f"https://example.com/sample/{i}",
                summary=summary,
                published=published,
                tags=tags,
            )
        )
    return upsert_articles(articles)


if __name__ == "__main__":
    n = seed()
    print(f"Seeded {n} sample articles.")
