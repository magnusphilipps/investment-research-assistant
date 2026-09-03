"""
news.py — Recent company news from Marketaux (Feature 8).

This module owns the external API request and converts Marketaux's response
into a small provider-neutral structure for the rest of the application.
It never prints output and never exposes the API token in errors or logs.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


MARKETAUX_NEWS_URL = "https://api.marketaux.com/v1/news/all"
REQUEST_TIMEOUT_SECONDS = 10
MAX_ARTICLES = 3
DESCRIPTION_MAX_CHARACTERS = 280
RECENCY_WINDOW_DAYS = 14

# Marketaux examples show incidental body-only associations around 10–40 and
# strong company-focused/title associations above 50. This is a v1 heuristic:
# keep it named and easy to tune as more real responses are observed.
MIN_RELEVANCE_MATCH_SCORE = 50.0

_NON_TERMINAL_ABBREVIATION_RE = re.compile(
    r"\b(?:inc|ltd|corp|co|llc|plc|n\.v|s\.a|mr|mrs|ms|dr|prof)\.$",
    re.IGNORECASE,
)


def _result(status: str, message: str, articles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the consistent result shape used by main.py and display.py."""
    return {
        "status": status,
        "message": message,
        "articles": articles or [],
    }


def _clean_text(value: Any) -> str:
    """Return readable single-line text, or an empty string for missing data."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def _shorten_description(value: Any) -> str:
    """
    Keep an API description short without cutting through a word.

    The first complete sentence(s) are preferred. If the source gives one
    unusually long sentence, a word boundary is used as a final fallback.
    """
    text = _clean_text(value)
    if not text:
        return text

    sentences: list[str] = []
    sentence_start = 0
    for match in re.finditer(r"[.!?](?=\s|$)", text):
        candidate = text[sentence_start:match.end()].strip()
        # A trailing "Inc." or similar abbreviation is not reliable sentence
        # evidence. Leaving it out avoids returning an API's cut-off fragment.
        if match.group() == "." and _NON_TERMINAL_ABBREVIATION_RE.search(candidate):
            continue
        sentences.append(candidate)
        sentence_start = match.end()

    selected = ""
    for sentence in sentences:
        candidate = f"{selected} {sentence}".strip()
        if len(candidate) > DESCRIPTION_MAX_CHARACTERS:
            break
        selected = candidate

    if selected:
        return selected

    shortened = text[:DESCRIPTION_MAX_CHARACTERS].rsplit(" ", 1)[0].rstrip(" ,;:")
    return shortened or text[:DESCRIPTION_MAX_CHARACTERS].rstrip()


def format_article_date(value: Any) -> str:
    """Format a Marketaux timestamp as ``2 Sep 2026`` without raising errors."""
    if not value:
        return "Date unavailable"

    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        # A date without a time is still useful, while malformed data is not.
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            return "Date unavailable"

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return f"{parsed.day} {parsed.strftime('%b %Y')}"


def _source_name(article: dict[str, Any]) -> str:
    """Read the publisher name across common Marketaux response shapes."""
    source = article.get("source")
    if isinstance(source, dict):
        source = source.get("name") or source.get("title")
    return _clean_text(source or article.get("source_name") or article.get("publisher"))


def _valid_url(value: Any) -> str | None:
    """Keep only ordinary HTTP(S) article URLs."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    if url.startswith(("https://", "http://")):
        return url
    return None


def _get_target_entity(article: dict[str, Any], ticker: str) -> dict[str, Any] | None:
    """Return the exact Marketaux entity for the searched ticker, if present."""
    entities = article.get("entities")
    if not isinstance(entities, list):
        return None

    target = ticker.upper()
    for entity in entities:
        if (
            isinstance(entity, dict)
            and str(entity.get("symbol") or "").upper() == target
        ):
            return entity
    return None


def _matches_ticker(article: dict[str, Any], ticker: str) -> bool:
    """
    Require a strong Marketaux entity association for the requested ticker.

    We do not search headline text for ticker letters: that would create false
    matches for ambiguous symbols such as C, CAT, and AI. Marketaux's
    ``match_score`` is the primary deterministic relevance signal. Articles
    with no entity, no score, or a weak score are rejected.
    """
    entity = _get_target_entity(article, ticker)
    if entity is None:
        return False

    try:
        match_score = float(entity.get("match_score"))
    except (TypeError, ValueError):
        return False
    return match_score >= MIN_RELEVANCE_MATCH_SCORE


def _recent_cutoff() -> str:
    """Return an ISO UTC cutoff so score sorting cannot surface stale news."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENCY_WINDOW_DAYS)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%S")


def _standardise_article(article: Any, ticker: str) -> dict[str, Any] | None:
    """Translate one Marketaux article into the application's simple format."""
    if not isinstance(article, dict) or not _matches_ticker(article, ticker):
        return None

    title = _clean_text(article.get("title"))
    if not title:
        return None

    return {
        "title": title,
        "source": _source_name(article),
        "published_at": article.get("published_at") or article.get("publishedAt"),
        "description": _shorten_description(
            article.get("description") or article.get("snippet")
        ),
        "url": _valid_url(article.get("url")),
    }


def _deduplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove repeated URLs and normalised headlines without extra requests."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []

    for article in articles:
        url = article.get("url")
        title_key = re.sub(r"\W+", " ", str(article.get("title", "")).lower()).strip()

        if url and url in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue

        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)
        unique.append(article)

        if len(unique) == MAX_ARTICLES:
            break

    return unique


def _publication_sort_key(article: dict[str, Any]) -> tuple[bool, datetime]:
    """Sort valid publication dates newest first and malformed dates last."""
    value = article.get("published_at")
    if not value:
        return False, datetime.min.replace(tzinfo=timezone.utc)

    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            return False, datetime.min.replace(tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return True, parsed.astimezone(timezone.utc)


def get_company_news(ticker: str) -> dict[str, Any]:
    """
    Fetch up to three recent, company-specific Marketaux articles.

    The API key comes from Replit Secrets through MARKETAUX_API_KEY. Expected
    service problems return ``status="unavailable"`` instead of raising, so
    Features 1–7 can continue normally.
    """
    api_token = os.environ.get("MARKETAUX_API_KEY")
    if not api_token:
        return _result(
            "unavailable",
            "Recent news temporarily unavailable.",
        )

    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return _result("empty", "No recent company-specific news found.")

    params = {
        "api_token": api_token,
        "symbols": symbol,
        "filter_entities": "true",
        "must_have_entities": "true",
        "min_match_score": MIN_RELEVANCE_MATCH_SCORE,
        "language": "en",
        "limit": MAX_ARTICLES,
        "published_after": _recent_cutoff(),
        "sort": "entity_match_score",
        "sort_order": "desc",
        "group_similar": "true",
    }

    try:
        response = requests.get(
            MARKETAUX_NEWS_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return _result("unavailable", "Recent news temporarily unavailable.")

    if not isinstance(payload, dict) or payload.get("error"):
        return _result("unavailable", "Recent news temporarily unavailable.")

    raw_articles = payload.get("data")
    if not isinstance(raw_articles, list):
        return _result("unavailable", "Recent news temporarily unavailable.")

    articles = [
        standardised
        for raw_article in raw_articles
        if (standardised := _standardise_article(raw_article, symbol)) is not None
    ]
    articles = _deduplicate_articles(articles)
    articles.sort(key=_publication_sort_key, reverse=True)

    if not articles:
        return _result("empty", "No recent company-specific news found.")
    return _result("ok", "", articles)