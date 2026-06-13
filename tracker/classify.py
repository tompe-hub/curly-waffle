"""Keyword-based tagging.

Tags are intentionally simple and transparent: an article is tagged ``ai`` or
``quantum`` if its title/summary mentions any of the relevant keywords (or the
source forces the tag), and ``china`` if it comes from a China-region source or
mentions a China-related keyword. This keeps classification explainable and easy
to tune by editing the keyword lists below.
"""

from __future__ import annotations

import re

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "large language model", "llm", "generative ai",
    "genai", "chatbot", "transformer", "foundation model", "gpt",
    "openai", "anthropic", "deepseek", "computer vision", "ai model",
    "ai agent", "agentic", "diffusion model", " ai ",
]

QUANTUM_KEYWORDS = [
    "quantum", "qubit", "superconducting", "entanglement",
    "quantum computing", "quantum supremacy", "quantum advantage",
    "quantum cryptography", "post-quantum", "qkd", "photonic",
]

CHINA_KEYWORDS = [
    "china", "chinese", "beijing", "shanghai", "shenzhen", "hong kong",
    "huawei", "alibaba", "baidu", "tencent", "bytedance", "deepseek",
    "smic", "xiaomi", "zte", "biren", "cambricon", "hygon", "loongson",
    "tsinghua", "byd", "moonshot", "zhipu", "01.ai", "yangtze",
]


def _compile(keywords: list[str]) -> re.Pattern[str]:
    # Match keywords as substrings, case-insensitively. Phrases with spaces are
    # matched literally; single tokens get word-ish boundaries to cut noise.
    parts = []
    for kw in keywords:
        if " " in kw or "." in kw:
            parts.append(re.escape(kw))
        else:
            parts.append(rf"\b{re.escape(kw)}\b")
    return re.compile("|".join(parts), re.IGNORECASE)


_AI_RE = _compile(AI_KEYWORDS)
_QUANTUM_RE = _compile(QUANTUM_KEYWORDS)
_CHINA_RE = _compile(CHINA_KEYWORDS)


def classify(title: str, summary: str, region: str, forced_tags: tuple[str, ...] = ()) -> list[str]:
    """Return the sorted list of tags for an article.

    Possible tags: ``ai``, ``quantum``, ``china``.
    """
    text = f"{title or ''} {summary or ''}"
    tags: set[str] = set(forced_tags)

    if _AI_RE.search(text):
        tags.add("ai")
    if _QUANTUM_RE.search(text):
        tags.add("quantum")
    if region == "china" or _CHINA_RE.search(text):
        tags.add("china")

    return sorted(tags)
