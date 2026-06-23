from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Iterable

import requests

from .models import TrendSignal

DEFAULT_SUBREDDITS = [
    "DidntKnowIWantedThat",
    "ShutUpAndTakeMyMoney",
    "INEEEEDIT",
    "BuyItForLife",
    "ProductPorn",
    "homegym",
    "gadgets",
]

STOPWORDS = {
    "about", "after", "again", "also", "amazon", "because", "before", "being", "best",
    "better", "could", "daily", "does", "done", "from", "good", "great", "have", "into",
    "just", "like", "made", "make", "more", "need", "new", "only", "other", "over", "really",
    "same", "some", "that", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "very", "want", "what", "when", "where", "which", "with", "would",
    "your", "you", "for", "and", "the", "are", "was", "but", "not", "can", "its", "it",
}


def fetch_subreddit_text(subreddit: str, limit: int = 25) -> str:
    url = f"https://www.reddit.com/r/{subreddit}/hot/.rss?limit={limit}"
    headers = {"User-Agent": "dropship-trend-finder/0.1 by a small business researcher"}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    titles: list[str] = []
    for elem in root.iter():
        if elem.tag.endswith("title") and elem.text:
            titles.append(elem.text)
    return "\n".join(titles)


def collect_reddit_text(subreddits: Iterable[str] = DEFAULT_SUBREDDITS, limit: int = 25) -> str:
    chunks: list[str] = []
    for subreddit in subreddits:
        try:
            chunks.append(fetch_subreddit_text(subreddit, limit=limit))
            time.sleep(0.4)  # polite delay
        except Exception as exc:  # noqa: BLE001 - keep the whole run from failing
            chunks.append(f"")
            print(f"Warning: failed to read r/{subreddit}: {exc}")
    return "\n".join(chunks).lower()


def count_keyword_mentions(keywords: Iterable[str], text: str) -> dict[str, TrendSignal]:
    output: dict[str, TrendSignal] = {}
    for keyword in keywords:
        normalized = keyword.lower().strip()
        if not normalized:
            continue
        # Phrase-safe count: portable blender should not match random separate words.
        pattern = re.compile(rf"\b{re.escape(normalized)}\b", flags=re.IGNORECASE)
        count = len(pattern.findall(text))
        output[normalized] = TrendSignal(keyword=normalized, mention_count=count, source="reddit_rss")
    return output


def discover_candidate_keywords(text: str, top_n: int = 30) -> list[str]:
    """Rough phrase discovery from RSS titles without heavyweight NLP dependencies."""
    words = [w for w in re.findall(r"[a-z][a-z0-9-]{2,}", text.lower()) if w not in STOPWORDS]
    phrases: Counter[str] = Counter()
    for size in (2, 3):
        for i in range(0, max(0, len(words) - size + 1)):
            phrase_words = words[i : i + size]
            if any(w in STOPWORDS for w in phrase_words):
                continue
            phrase = " ".join(phrase_words)
            phrases[phrase] += 1
    return [phrase for phrase, _ in phrases.most_common(top_n)]
