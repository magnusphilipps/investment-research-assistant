"""Historical stock-price performance calculations.

This module retrieves adjusted historical prices and turns them into the
structured values used by the terminal display.  It does not print anything,
which keeps network access and calculations separate from presentation.
"""

from datetime import datetime

import pandas as pd
import yfinance as yf


PERFORMANCE_PERIODS = {
    "1 Month": pd.DateOffset(months=1),
    "6 Months": pd.DateOffset(months=6),
    "1 Year": pd.DateOffset(years=1),
    "3 Years": pd.DateOffset(years=3),
    "5 Years": pd.DateOffset(years=5),
}


def _clean_history(history: pd.DataFrame) -> pd.DataFrame:
    """Return clean adjusted close, close, high, and low price columns."""
    required_columns = {"Adj Close", "Close", "High", "Low"}
    if history is None or history.empty or not required_columns.issubset(history.columns):
        return pd.DataFrame(columns=sorted(required_columns))

    cleaned = history[list(required_columns)].apply(pd.to_numeric, errors="coerce").dropna()
    cleaned = cleaned[(cleaned > 0).all(axis=1)]
    if cleaned.empty:
        return pd.DataFrame(columns=sorted(required_columns))

    # Normalising dates makes comparisons work with both timezone-aware and
    # timezone-naive data returned by different yfinance versions.
    dates = pd.to_datetime(cleaned.index)
    if getattr(dates, "tz", None) is not None:
        dates = dates.tz_localize(None)
    cleaned.index = dates.normalize()
    return cleaned[~cleaned.index.duplicated(keep="last")].sort_index()


def _price_on_or_before(prices: pd.Series, target_date: pd.Timestamp) -> float | None:
    """Find the last available trading price on or before ``target_date``."""
    if prices.empty:
        return None

    target_date = pd.Timestamp(target_date).tz_localize(None).normalize()
    position = prices.index.searchsorted(target_date, side="right") - 1
    if position < 0:
        return None
    return float(prices.iloc[position])


def calculate_return(
    prices: pd.Series,
    period_offset: pd.DateOffset,
    latest_date: pd.Timestamp | None = None,
) -> float | None:
    """Calculate ``ending / starting - 1`` for a trading-date period.

    The start date is a calendar date, but the price is taken from the last
    trading day on or before it.  This avoids assuming that weekends and
    holidays have prices.  Returning ``None`` means there is not enough real
    history; callers should display that as ``N/A`` rather than zero.
    """
    if prices.empty:
        return None

    end_date = pd.Timestamp(latest_date) if latest_date is not None else prices.index[-1]
    end_date = end_date.tz_localize(None).normalize()
    end_price = _price_on_or_before(prices, end_date)
    start_price = _price_on_or_before(prices, end_date - period_offset)

    if start_price is None or end_price is None or start_price == 0:
        return None
    return (end_price / start_price) - 1


def _calculate_52_week_range(history: pd.DataFrame) -> dict:
    """Calculate the range from raw daily High and Low prices."""
    if history.empty:
        return {
            "current_price": None,
            "high": None,
            "low": None,
            "below_high": None,
            "above_low": None,
        }

    latest_date = history.index[-1]
    window_start = latest_date - pd.DateOffset(weeks=52)
    window = history[history.index >= window_start]
    current_price = float(history["Close"].iloc[-1])
    high = float(window["High"].max()) if not window.empty else None
    low = float(window["Low"].min()) if not window.empty else None

    return {
        "current_price": current_price,
        "high": high,
        "low": low,
        "below_high": (high - current_price) / high if high else None,
        "above_low": (current_price - low) / low if low else None,
    }


def _history_for_ticker(ticker_symbol: str) -> pd.DataFrame:
    """Download prices and apply Yahoo's earliest known trade date, if given."""
    ticker = yf.Ticker(ticker_symbol)
    history = ticker.history(
        period="max",
        auto_adjust=False,
        actions=False,
    )
    cleaned = _clean_history(history)
    if cleaned.empty:
        return cleaned

    # This metadata is a boundary for Yahoo's price series, not proof that
    # the current company existed then. It helps reject rows before Yahoo's
    # known first trade while avoiding an unreliable ticker-specific guess.
    try:
        first_trade = ticker.get_history_metadata().get("firstTradeDate")
    except Exception:
        first_trade = None
    if first_trade:
        first_trade_date = pd.to_datetime(first_trade, unit="s", errors="coerce")
        if pd.notna(first_trade_date):
            cleaned = cleaned[cleaned.index >= first_trade_date.tz_localize(None).normalize()]
    return cleaned


def get_performance(ticker_symbol: str) -> dict | None:
    """Retrieve stock and S&P 500 performance for a ticker.

    The stock history is required for a result.  The benchmark is optional:
    a Yahoo Finance benchmark failure leaves the stock section available and
    marks benchmark values as unavailable.
    """
    stock_history = _history_for_ticker(ticker_symbol)
    if stock_history.empty:
        return None
    stock_prices = stock_history["Adj Close"]

    stock_returns = {
        label: calculate_return(stock_prices, offset)
        for label, offset in PERFORMANCE_PERIODS.items()
    }

    try:
        benchmark_history = _history_for_ticker("^GSPC")
    except Exception:
        benchmark_history = pd.DataFrame()
    benchmark_prices = (
        benchmark_history["Adj Close"] if not benchmark_history.empty else pd.Series(dtype="float64")
    )

    benchmark_returns = {
        label: calculate_return(benchmark_prices, PERFORMANCE_PERIODS[label])
        if not benchmark_prices.empty and label in ("1 Year", "3 Years", "5 Years")
        else None
        for label in ("1 Year", "3 Years", "5 Years")
    }
    comparison = {}
    for label in benchmark_returns:
        stock_return = stock_returns[label]
        benchmark_return = benchmark_returns[label]
        # Do not show a benchmark number as a comparison when the stock has
        # no valid history for that same period.
        if stock_return is None:
            benchmark_return = None
        difference = (
            stock_return - benchmark_return
            if stock_return is not None and benchmark_return is not None
            else None
        )
        comparison[label] = {
            "stock": stock_return,
            "benchmark": benchmark_return,
            "difference": difference,
        }

    return {
        "returns": stock_returns,
        "range": _calculate_52_week_range(stock_history),
        "benchmark": comparison,
        "latest_date": stock_history.index[-1].date().isoformat(),
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
    }