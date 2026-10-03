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

import yfinance as yf  # Third-party library for fetching stock data


def is_not_found_error(error: Exception) -> bool:
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

    # Create a Ticker object. This does not make a network request yet —
    # it just prepares yfinance to look up this symbol.
    ticker = yf.Ticker(ticker_symbol)

    # .info is a property that triggers the actual network request.
    # It returns a large dictionary of company data from Yahoo Finance.
    # Importantly, this single call returns ALL the data we need for
    # both Phase 1 (price) and Phase 2 (overview) — no extra requests.
    try:
        info = ticker.info
    except Exception as error:
        if is_not_found_error(error):
            return None
        raise

    # Yahoo may return the requested symbol even when it has no security record.
    if not isinstance(info, dict) or not is_resolved_security(ticker_symbol, info):
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
