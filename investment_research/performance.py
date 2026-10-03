"""Historical stock-price performance calculations.

This module retrieves adjusted historical prices and turns them into the
structured values used by the terminal display.  It does not print anything,
which keeps network access and calculations separate from presentation.
"""

import math
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

_BENCHMARKS_BY_EXCHANGE = {
    "ASE": ("^GSPC", "S&P 500"),
    "NASDAQ": ("^GSPC", "S&P 500"),
    "NASDAQGS": ("^GSPC", "S&P 500"),
    "NASDAQGM": ("^GSPC", "S&P 500"),
    "NASDAQCM": ("^GSPC", "S&P 500"),
    "NCM": ("^GSPC", "S&P 500"),
    "NGM": ("^GSPC", "S&P 500"),
    "NMS": ("^GSPC", "S&P 500"),
    "NAS": ("^GSPC", "S&P 500"),
    "NYQ": ("^GSPC", "S&P 500"),
    "NYSE": ("^GSPC", "S&P 500"),
    "NEWYORKSTOCKEXCHANGE": ("^GSPC", "S&P 500"),
    "NYSEARCA": ("^GSPC", "S&P 500"),
    "NYSEAMERICAN": ("^GSPC", "S&P 500"),
    "PCX": ("^GSPC", "S&P 500"),
    "LSE": ("^FTSE", "FTSE 100"),
    "XLON": ("^FTSE", "FTSE 100"),
    "LONDONSTOCKEXCHANGE": ("^FTSE", "FTSE 100"),
    "JPX": ("^N225", "Nikkei 225"),
    "TYO": ("^N225", "Nikkei 225"),
    "HKG": ("^HSI", "Hang Seng Index"),
    "HONGKONGSTOCKEXCHANGE": ("^HSI", "Hang Seng Index"),
    "TOR": ("^GSPTSE", "S&P/TSX Composite"),
    "TSX": ("^GSPTSE", "S&P/TSX Composite"),
    "TORONTOSTOCKEXCHANGE": ("^GSPTSE", "S&P/TSX Composite"),
    "ASX": ("^AXJO", "S&P/ASX 200"),
    "GER": ("^GDAXI", "DAX"),
    "XETRA": ("^GDAXI", "DAX"),
    "FRANKFURTSTOCKEXCHANGE": ("^GDAXI", "DAX"),
    "PAR": ("^FCHI", "CAC 40"),
    "AMS": ("^AEX", "AEX"),
    "MIL": ("FTSEMIB.MI", "FTSE MIB"),
    "STO": ("^OMX", "OMX Stockholm 30"),
    "SWX": ("^SSMI", "SMI"),
    "SIX": ("^SSMI", "SMI"),
    "NSE": ("^NSEI", "NIFTY 50"),
    "BSE": ("^BSESN", "BSE SENSEX"),
    "KSC": ("^KS11", "KOSPI"),
    "KOE": ("^KQ11", "KOSDAQ"),
    "SES": ("^STI", "Straits Times Index"),
}

_BENCHMARKS_BY_MARKET = {
    "US_MARKET": ("^GSPC", "S&P 500"),
    "GB_MARKET": ("^FTSE", "FTSE 100"),
    "JP_MARKET": ("^N225", "Nikkei 225"),
    "HK_MARKET": ("^HSI", "Hang Seng Index"),
    "CA_MARKET": ("^GSPTSE", "S&P/TSX Composite"),
    "AU_MARKET": ("^AXJO", "S&P/ASX 200"),
    "DE_MARKET": ("^GDAXI", "DAX"),
    "FR_MARKET": ("^FCHI", "CAC 40"),
    "IN_MARKET": ("^NSEI", "NIFTY 50"),
    "CH_MARKET": ("^SSMI", "SMI"),
    "KR_MARKET": ("^KS11", "KOSPI"),
    "SG_MARKET": ("^STI", "Straits Times Index"),
}


def _benchmark_for_listing(
    exchange: str | None,
    market: str | None,
) -> tuple[str, str, str]:
    """Choose a broad local index, falling back explicitly when listing data is absent."""
    exchange_key = "".join(character for character in str(exchange or "").upper() if character.isalnum())
    market_key = str(market or "").strip().upper()
    benchmark = _BENCHMARKS_BY_EXCHANGE.get(exchange_key)
    if benchmark is None:
        benchmark = _BENCHMARKS_BY_MARKET.get(market_key)
    if benchmark is not None:
        return (*benchmark, "listing_market")
    return "^GSPC", "S&P 500 (fallback)", "fallback"


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


def _daily_return_series(prices: pd.Series) -> pd.Series:
    """Return a clean series of daily returns for volatility calculations."""
    if prices.empty:
        return pd.Series(dtype="float64")
    returns = prices.pct_change().dropna()
    if returns.empty:
        return returns
    returns = returns[returns.map(lambda value: math.isfinite(float(value)))]
    return returns.astype(float)


def _annualized_volatility(daily_returns: pd.Series) -> float | None:
    """Convert a daily-return series into annualized volatility."""
    if daily_returns.empty or len(daily_returns) < 2:
        return None
    std_dev = daily_returns.std(ddof=1)
    if pd.isna(std_dev) or std_dev <= 0:
        return None
    return float(std_dev * math.sqrt(252))


def _beta_for_prices(stock_prices: pd.Series, benchmark_prices: pd.Series) -> float | None:
    """Estimate beta using the stock and benchmark daily return covariance."""
    if stock_prices.empty or benchmark_prices.empty:
        return None
    aligned = pd.concat({"stock": stock_prices, "benchmark": benchmark_prices}, axis=1, sort=False).dropna()
    if aligned.empty:
        return None
    stock_returns = aligned["stock"].pct_change().dropna()
    benchmark_returns = aligned["benchmark"].pct_change().dropna()
    if stock_returns.empty or benchmark_returns.empty:
        return None
    combined = pd.concat({"stock": stock_returns, "benchmark": benchmark_returns}, axis=1, sort=False).dropna()
    if combined.empty or len(combined) < 2:
        return None
    benchmark_variance = combined["benchmark"].var(ddof=1)
    if pd.isna(benchmark_variance) or benchmark_variance == 0:
        return None
    beta = combined["stock"].cov(combined["benchmark"]) / benchmark_variance
    return float(beta) if pd.notna(beta) else None


def _max_drawdown(prices: pd.Series) -> float | None:
    """Return the worst peak-to-trough drawdown over the observation window."""
    if prices.empty:
        return None
    drawdowns = prices / prices.cummax() - 1
    if drawdowns.empty:
        return None
    max_drawdown = float(drawdowns.min())
    return max_drawdown if pd.notna(max_drawdown) else None


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


def get_performance(
    ticker_symbol: str,
    exchange: str | None = None,
    market: str | None = None,
) -> dict | None:
    """Retrieve stock performance against a broad benchmark for its listing market.

    The stock history is required for a result.  The benchmark is optional:
    a Yahoo Finance benchmark failure leaves the stock section available and
    marks benchmark values as unavailable.
    """
    benchmark_symbol, benchmark_name, benchmark_source = _benchmark_for_listing(exchange, market)
    stock_history = _history_for_ticker(ticker_symbol)
    if stock_history.empty:
        return None
    stock_prices = stock_history["Adj Close"]
    stock_daily_returns = _daily_return_series(stock_prices)

    stock_returns = {
        label: calculate_return(stock_prices, offset)
        for label, offset in PERFORMANCE_PERIODS.items()
    }

    try:
        benchmark_history = _history_for_ticker(benchmark_symbol)
    except Exception:
        benchmark_history = pd.DataFrame()
    benchmark_prices = (
        benchmark_history["Adj Close"] if not benchmark_history.empty else pd.Series(dtype="float64")
    )
    benchmark_daily_returns = _daily_return_series(benchmark_prices)

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
        "daily_returns": stock_daily_returns.tolist(),
        "annualized_volatility": _annualized_volatility(stock_daily_returns),
        "beta": _beta_for_prices(stock_prices, benchmark_prices),
        "max_drawdown": _max_drawdown(stock_prices),
        "range": _calculate_52_week_range(stock_history),
        "benchmark": comparison,
        "benchmark_symbol": benchmark_symbol,
        "benchmark_name": benchmark_name,
        "benchmark_source": benchmark_source,
        "latest_date": stock_history.index[-1].date().isoformat(),
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
    }