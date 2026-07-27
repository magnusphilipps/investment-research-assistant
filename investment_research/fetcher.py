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
# ============================================================

import yfinance as yf  # Third-party library for fetching stock data


def get_stock_info(ticker_symbol: str) -> dict | None:
    """
    Fetch basic information for a given stock ticker symbol.

    A "dict" (dictionary) is a Python data structure that stores
    key-value pairs, like:
        {"name": "Apple Inc.", "price": 195.50}

    Parameters:
        ticker_symbol (str): The stock ticker, e.g. "AAPL" or "MSFT"

    Returns:
        A dictionary with keys: "ticker", "name", "price", "market_cap"
        Returns None if the ticker is invalid or data is unavailable.
    """

    # Create a Ticker object. This does not make a network request yet —
    # it just prepares yfinance to look up this symbol.
    ticker = yf.Ticker(ticker_symbol)

    # .info is a property that triggers the actual network request.
    # It returns a large dictionary of company data from Yahoo Finance.
    info = ticker.info

    # Yahoo Finance returns a mostly-empty dict for invalid tickers.
    # We check for "symbol" as a signal that we got real data back.
    if not info or "symbol" not in info:
        return None

    # Pull out just the three fields we care about.
    # .get("key", fallback) safely retrieves a value — if the key
    # doesn't exist, it returns the fallback instead of crashing.
    name       = info.get("longName") or info.get("shortName") or "Unknown"
    price      = info.get("currentPrice") or info.get("regularMarketPrice")
    market_cap = info.get("marketCap")

    # Build and return a tidy dictionary with only what we need.
    return {
        "ticker":     ticker_symbol.upper(),
        "name":       name,
        "price":      price,
        "market_cap": market_cap,
    }
