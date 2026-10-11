"""Resolve ticker or company-name input using Yahoo Finance symbol search."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re
import logging
from threading import Lock
from typing import Literal

import yfinance as yf

from . import diagnostics


MAX_CANDIDATES = 3
LOGGER = logging.getLogger(__name__)
_CACHE_MAX_ENTRIES = 256
_SCORE_LEAD_RATIO = 1.01
_SYMBOL_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9.^=-]{0,19}\Z")
_TICKER_INPUT_PATTERN = re.compile(r"[A-Za-z0-9.^=-]+\Z")


@dataclass(frozen=True)
class SecurityCandidate:
    ticker: str
    company_name: str
    exchange: str | None = None


@dataclass(frozen=True)
class TickerResolution:
    status: Literal["resolved", "ambiguous", "not_found"]
    ticker: str | None = None
    candidates: tuple[SecurityCandidate, ...] = ()


class TickerResolutionError(Exception):
    """Raised when the symbol-search provider cannot complete a lookup."""


@dataclass(frozen=True)
class _SearchCandidate:
    security: SecurityCandidate
    score: float | None
    order: int


_resolution_cache: OrderedDict[str, TickerResolution] = OrderedDict()
_cache_lock = Lock()


def _normalize_input(value: str) -> str:
    return " ".join(value.split())


def _cache_key(value: str) -> str:
    return _normalize_input(value).casefold()


def _cache_success(key: str, result: TickerResolution) -> None:
    with _cache_lock:
        _resolution_cache[key] = result
        _resolution_cache.move_to_end(key)
        while len(_resolution_cache) > _CACHE_MAX_ENTRIES:
            _resolution_cache.popitem(last=False)


def _cached_success(key: str) -> TickerResolution | None:
    with _cache_lock:
        result = _resolution_cache.get(key)
        if result is not None:
            _resolution_cache.move_to_end(key)
        return result


def clear_resolution_cache() -> None:
    """Clear successful local resolutions, primarily for deterministic tests."""
    with _cache_lock:
        _resolution_cache.clear()


def _is_canonical_symbol(value: str) -> bool:
    symbol = value.upper()
    return bool(
        _SYMBOL_PATTERN.fullmatch(symbol)
        and re.search(r"[.-][A-Z0-9]", symbol)
    )


def _normalized_words(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _matches_company_name(query: str, company_name: str) -> bool:
    query_words = _normalized_words(query)
    name_words = _normalized_words(company_name)
    if not query_words or not name_words:
        return False
    if len(query_words) == 1:
        return name_words[0].startswith(query_words[0])
    return all(word in name_words for word in query_words)


def _search_candidates(query: str) -> list[_SearchCandidate]:
    try:
        quotes = yf.Search(
            query,
            max_results=12,
            news_count=0,
            lists_count=0,
            include_cb=False,
            include_nav_links=False,
            include_research=False,
            enable_fuzzy_query=True,
            timeout=10,
        ).quotes
    except Exception as error:
        diagnostics.log_exception(LOGGER, "ticker_symbol_search", error)
        raise TickerResolutionError("Yahoo Finance symbol search failed.") from error

    candidates: list[_SearchCandidate] = []
    seen: set[str] = set()
    for order, quote in enumerate(quotes):
        if not isinstance(quote, dict) or str(quote.get("quoteType") or "").upper() != "EQUITY":
            continue
        symbol = str(quote.get("symbol") or "").strip().upper()
        if not _SYMBOL_PATTERN.fullmatch(symbol) or symbol in seen:
            continue
        seen.add(symbol)

        name = str(
            quote.get("longname")
            or quote.get("longName")
            or quote.get("shortname")
            or quote.get("shortName")
            or symbol
        ).strip()
        exchange = str(
            quote.get("exchDisp")
            or quote.get("fullExchangeName")
            or quote.get("exchange")
            or ""
        ).strip() or None
        score_value = quote.get("score")
        try:
            score = float(score_value) if score_value is not None else None
        except (TypeError, ValueError):
            score = None
        candidates.append(
            _SearchCandidate(
                SecurityCandidate(ticker=symbol, company_name=name, exchange=exchange),
                score,
                order,
            )
        )
    return candidates


def _rank(candidates: list[_SearchCandidate]) -> list[_SearchCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.score is None,
            -(candidate.score or 0.0),
            candidate.order,
        ),
    )


def _is_clear_provider_leader(
    ranked: list[_SearchCandidate],
) -> bool:
    if len(ranked) == 1:
        return True
    first_score = ranked[0].score
    second_score = ranked[1].score
    return (
        first_score is not None
        and second_score is not None
        and second_score > 0
        and first_score / second_score >= _SCORE_LEAD_RATIO
    )


def resolve_security_input(user_input: str) -> TickerResolution:
    """Resolve a ticker or company name without starting the report pipeline."""
    normalized = _normalize_input(user_input)
    if not normalized:
        return TickerResolution(status="not_found")

    key = _cache_key(normalized)
    cached = _cached_success(key)
    if cached is not None:
        return cached

    if _is_canonical_symbol(normalized):
        result = TickerResolution(status="resolved", ticker=normalized.upper())
        _cache_success(key, result)
        return result

    query = normalized.upper() if _TICKER_INPUT_PATTERN.fullmatch(normalized) else normalized
    search_candidates = _search_candidates(query)
    exact_symbol = query.upper()
    exact_matches = [
        candidate
        for candidate in search_candidates
        if candidate.security.ticker == exact_symbol
    ]
    if exact_matches:
        result = TickerResolution(status="resolved", ticker=exact_symbol)
        _cache_success(key, result)
        return result

    if _TICKER_INPUT_PATTERN.fullmatch(normalized):
        stem_matches = [
            candidate
            for candidate in search_candidates
            if candidate.security.ticker.startswith(exact_symbol)
            and len(candidate.security.ticker) > len(exact_symbol)
            and candidate.security.ticker[len(exact_symbol)] in ".-"
        ]
        ranked_stem_matches = _rank(stem_matches)
        if ranked_stem_matches and _is_clear_provider_leader(ranked_stem_matches):
            result = TickerResolution(
                status="resolved",
                ticker=ranked_stem_matches[0].security.ticker,
            )
            _cache_success(key, result)
            return result

    matching = [
        candidate
        for candidate in search_candidates
        if _matches_company_name(normalized, candidate.security.company_name)
    ]
    ranked_matches = _rank(matching)
    if not ranked_matches:
        return TickerResolution(status="not_found")

    candidates = tuple(
        candidate.security for candidate in ranked_matches[:MAX_CANDIDATES]
    )
    if len(candidates) == 1:
        result = TickerResolution(status="resolved", ticker=candidates[0].ticker)
        _cache_success(key, result)
        return result
    return TickerResolution(status="ambiguous", candidates=candidates)
