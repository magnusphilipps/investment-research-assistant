# ============================================================
# fetcher.py — Stock Data Fetcher
# ============================================================
#
# PURPOSE:
#   This module is responsible for one thing only: fetching
#   stock data from the internet using the yfinance library.
#
#   Keeping data-fetching code in its own file is good practice.
#   If you ever want to switch to a different data source, you
#   only need to change this file — nothing else.
#
# HOW IT WORKS:
#   yfinance connects to Yahoo Finance and downloads information
#   about publicly traded companies. You give it a ticker symbol
#   (like "AAPL" for Apple) and it returns a Ticker object full
#   of data you can query.
#
# FEATURES RETURNED:
#   Phase 1 — ticker, name, price, market_cap
#   Phase 2 — sector, industry, country, employees, website, description
# ============================================================

import logging
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable

import yfinance as yf  # Third-party library for fetching stock data

from . import diagnostics

LOGGER = logging.getLogger(__name__)
YAHOO_INFO_CACHE_TTL_SECONDS = 60 * 60
YAHOO_INFO_CACHE_MAX_ENTRIES = 256
YAHOO_MAX_ATTEMPTS = 3
YAHOO_RETRY_DELAYS_SECONDS = (1, 2)


class YahooRateLimitError(Exception):
    """Raised when Yahoo Finance remains rate-limited after bounded retries."""


_yahoo_info_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_yahoo_info_cache_lock = Lock()


def is_rate_limit_error(error: Exception) -> bool:
    """Identify Yahoo HTTP 429 and equivalent provider rate-limit errors."""
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    error_text = f"{type(error).__name__} {error}".casefold()
    return any(
        marker in error_text
        for marker in ("too many requests", "http 429", "rate limited", "rate limit")
    )


def run_with_rate_limit_retry(
    operation: Callable[[], Any],
    stage: str,
) -> Any:
    """Retry only Yahoo rate limits, with at most three total attempts."""
    for attempt in range(YAHOO_MAX_ATTEMPTS):
        try:
            return operation()
        except Exception as error:
            if is_not_found_error(error):
                LOGGER.info("%s invalid_ticker", stage)
                raise
            if not is_rate_limit_error(error):
                diagnostics.log_exception(LOGGER, f"{stage}_provider_error", error)
                raise
            LOGGER.warning(
                "%s yahoo_rate_limited: attempt=%d/%d",
                stage,
                attempt + 1,
                YAHOO_MAX_ATTEMPTS,
            )
            if attempt == YAHOO_MAX_ATTEMPTS - 1:
                raise YahooRateLimitError(
                    "Yahoo Finance is temporarily rate-limited."
                ) from error
            time.sleep(YAHOO_RETRY_DELAYS_SECONDS[attempt])
    raise RuntimeError("Yahoo retry loop exited unexpectedly.")


def clear_yahoo_info_cache() -> None:
    """Clear cached Yahoo metadata, primarily for deterministic tests."""
    with _yahoo_info_cache_lock:
        _yahoo_info_cache.clear()


def is_not_found_error(error: Exception) -> bool:
    if is_rate_limit_error(error):
        return False
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) == 404:
        return True
    return type(error).__name__ in {"YFTickerMissingError", "YFPricesMissingError"}


def is_resolved_security(ticker_symbol: str, info: dict) -> bool:
    """Require a matching provider symbol plus independent security identity evidence."""
    resolved_symbol = str(info.get("symbol") or "").strip().upper().replace(".", "-")
    requested_symbol = str(ticker_symbol).strip().upper().replace(".", "-")
    if not resolved_symbol or resolved_symbol != requested_symbol:
        return False

    names = (info.get("longName"), info.get("shortName"))
    has_company_name = any(
        isinstance(name, str)
        and name.strip()
        and name.strip().casefold() not in {
            "unknown", "n/a", "not available", requested_symbol.casefold(),
        }
        for name in names
    )
    quote_type = str(info.get("quoteType") or "").strip().upper()
    has_equity_listing = quote_type == "EQUITY" and bool(
        info.get("exchange") or info.get("fullExchangeName") or info.get("market")
    )
    return has_company_name or has_equity_listing


def get_yahoo_info(ticker_symbol: str) -> dict[str, Any] | None:
    """Return validated Yahoo ticker metadata, retrying and caching successful lookups."""
    symbol = ticker_symbol.strip().upper()
    if not symbol:
        return None

    now = time.monotonic()
    with _yahoo_info_cache_lock:
        cached = _yahoo_info_cache.get(symbol)
        if cached is not None:
            expires_at, info = cached
            if now < expires_at:
                _yahoo_info_cache.move_to_end(symbol)
                LOGGER.info("Yahoo company metadata cache_hit: ticker=%s", symbol)
                return info.copy()
            del _yahoo_info_cache[symbol]

    LOGGER.info("Yahoo company metadata lookup started: ticker=%s", symbol)
    ticker = yf.Ticker(symbol)
    info = run_with_rate_limit_retry(lambda: ticker.info, "yahoo_company_metadata")
    if not isinstance(info, dict) or not is_resolved_security(symbol, info):
        LOGGER.warning("Yahoo company metadata invalid_ticker: ticker=%s", symbol)
        return info if isinstance(info, dict) else None

    with _yahoo_info_cache_lock:
        _yahoo_info_cache[symbol] = (
            time.monotonic() + YAHOO_INFO_CACHE_TTL_SECONDS,
            info.copy(),
        )
        _yahoo_info_cache.move_to_end(symbol)
        while len(_yahoo_info_cache) > YAHOO_INFO_CACHE_MAX_ENTRIES:
            _yahoo_info_cache.popitem(last=False)
    LOGGER.info("Yahoo company metadata lookup succeeded: ticker=%s", symbol)
    return info.copy()


def get_stock_info(ticker_symbol: str) -> dict | None:
    """
    Fetch stock and company overview information for a given ticker symbol.

    A "dict" (dictionary) is a Python data structure that stores
    key-value pairs, like:
        {"name": "Apple Inc.", "price": 195.50}

    Parameters:
        ticker_symbol (str): The stock ticker, e.g. "AAPL" or "MSFT"

    Returns:
        A dictionary with all Phase 1 and Phase 2 fields.
        Returns None if the ticker is invalid or data is unavailable.
    """

    try:
        info = get_yahoo_info(ticker_symbol)
    except Exception as error:
        if isinstance(error, YahooRateLimitError):
            LOGGER.error("Company lookup yahoo_rate_limited: ticker=%s", ticker_symbol)
            raise
        if is_not_found_error(error):
            LOGGER.info("Company lookup invalid_ticker: ticker=%s", ticker_symbol)
            return None
        LOGGER.error("Company lookup provider_error: ticker=%s", ticker_symbol)
        raise

    # Yahoo may return the requested symbol even when it has no security record.
    if not isinstance(info, dict) or not is_resolved_security(ticker_symbol, info):
        LOGGER.warning(
            "Company lookup rejected provider result: ticker=%s result_is_dict=%s",
            ticker_symbol,
            isinstance(info, dict),
        )
        return None

    # ----------------------------------------------------------------
    # Phase 1 fields — price snapshot
    # ----------------------------------------------------------------

    # .get("key", fallback) safely retrieves a value — if the key
    # doesn't exist, it returns the fallback instead of crashing.
    name       = info.get("longName") or info.get("shortName") or "Unknown"
    price      = info.get("currentPrice") or info.get("regularMarketPrice")
    market_cap = info.get("marketCap")

    # ----------------------------------------------------------------
    # Phase 2 fields — company overview
    #
    # Each line follows the same pattern:
    #   variable = info.get("yahoo_key")
    #
    # If Yahoo Finance does not supply a value for that key, .get()
    # returns None. The display module handles None gracefully by
    # showing "N/A", so we never need to crash or guess a default here.
    # ----------------------------------------------------------------

    sector      = info.get("sector")       # e.g. "Technology"
    industry    = info.get("industry")     # e.g. "Consumer Electronics"
    country     = info.get("country")      # e.g. "United States"
    employees   = info.get("fullTimeEmployees")   # e.g. 161000 (integer)
    website     = info.get("website")      # e.g. "https://www.apple.com"
    description = info.get("longBusinessSummary")  # Multi-sentence paragraph

    # Build and return a single tidy dictionary covering both phases.
    # Using one dictionary means main.py and display.py only ever handle
    # one object — there is no need to pass multiple return values around.
    return {
        # Phase 1
        "ticker":      ticker_symbol.upper(),
        "name":        name,
        "price":       price,
        "market_cap":  market_cap,
        "currency":    info.get("currency"),
        # Phase 2
        "sector":      sector,
        "industry":    industry,
        "country":     country,
        "exchange":    info.get("exchange") or info.get("fullExchangeName"),
        "market":      info.get("market"),
        "employees":   employees,
        "website":     website,
        "description": description,
    }
