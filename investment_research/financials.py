# ============================================================
# financials.py — Financial Statements
# ============================================================
#
# PURPOSE:
#   This module fetches and calculates the three core financial
#   statements for a given company:
#     A. Income statement  — revenue, margins, EPS
#     B. Balance sheet     — assets, liabilities, ratios
#     C. Cash flow         — operating CF, CapEx, free cash flow
#
# WHY A SEPARATE MODULE?
#   Financial statements require different yfinance data sources
#   (.financials, .balance_sheet, .cashflow) and involve their
#   own calculations (margins, ratios, growth rates).  Keeping
#   this logic separate from fetcher.py (which handles the price
#   and overview snapshot) respects the Single Responsibility
#   Principle — each module owns one clear job.
#
# DATA SOURCE:
#   yfinance returns financial statements as pandas DataFrames.
#   Rows are accounting line items; columns are annual periods
#   (most recent first).  Line-item names vary between companies
#   and yfinance versions, so every extraction uses a helper
#   that tries a ranked list of candidate label names.
#
# STRUCTURE:
#   _get_currency_symbol()  — maps currency code to display symbol
#   _extract_value()        — robust label-tolerant row lookup
#   _safe_divide()          — division that handles None and zero
#   _pct()                  — shorthand for percentage calculation
#   _compute_income()       — income statement extraction + calcs
#   _compute_balance()      — balance sheet extraction + calcs
#   _compute_cashflow()     — cash flow extraction + calcs
#   get_financial_statements() — public entry point
# ============================================================

import yfinance as yf   # Third-party: fetches financial data
import pandas as pd     # Third-party: DataFrames returned by yfinance


# ------------------------------------------------------------
# Currency symbol lookup
# ------------------------------------------------------------
# Maps ISO 4217 currency codes (what yfinance returns) to the
# display symbols used in output.  If a code is not in this
# table, the code itself is used as a prefix (e.g. "SEK 12.3B").

_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "GBP": "£",
    "EUR": "€",
    "JPY": "¥",
    "CNY": "¥",
    "CAD": "C$",
    "AUD": "A$",
    "CHF": "CHF",
    "HKD": "HK$",
    "INR": "₹",
    "KRW": "₩",
    "SGD": "S$",
    "MXN": "MX$",
    "BRL": "R$",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
}


def _get_currency_symbol(info: dict) -> tuple[str, str]:
    """
    Return (currency_code, currency_symbol) from a yfinance info dict.

    "financialCurrency" is the currency used in the company's
    financial statements (e.g. Apple reports in USD even though
    it sells globally).

    Falls back to "USD" / "$" if the field is missing.
    """
    code   = info.get("financialCurrency") or "USD"
    symbol = _CURRENCY_SYMBOLS.get(code, code + " ")
    return code, symbol


# ------------------------------------------------------------
# Core data-extraction helpers
# ------------------------------------------------------------

def _extract_value(
    df,
    candidate_labels: list[str],
    col_index: int = 0,
) -> float | None:
    """
    Search a yfinance DataFrame for the first matching row label.

    WHY THIS EXISTS:
        yfinance uses different label strings across companies and
        library versions.  For example, "Total Revenue" might appear
        as "TotalRevenue" or "Revenue" for different tickers.
        Rather than hardcoding one label and crashing when it is
        absent, we try a ranked list of alternatives.

    Parameters:
        df               : pandas DataFrame (income stmt, balance, etc.)
        candidate_labels : List of label strings to try, most
                           preferred first.
        col_index        : Column to read (0 = most recent year).

    Returns:
        float if a matching, non-NaN value is found; None otherwise.
    """
    if df is None or df.empty:
        return None

    for label in candidate_labels:
        if label in df.index:
            try:
                value = df.loc[label].iloc[col_index]
                # pandas uses NaN (Not a Number) for missing cells.
                # pd.notna() returns True for anything that is not NaN.
                if pd.notna(value):
                    return float(value)
            except (IndexError, KeyError, TypeError):
                # IndexError  : col_index beyond available columns
                # KeyError    : label exists but loc fails (edge case)
                # TypeError   : value cannot be cast to float
                continue

    return None


def _safe_divide(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    """
    Divide two numbers safely, returning None instead of crashing.

    Division is unsafe when:
      - Either value is None (data was unavailable)
      - The denominator is zero (e.g. a company with zero revenue)

    Returning None means the caller can display "N/A" rather than
    showing a misleading result.
    """
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    """
    Calculate a percentage (numerator / denominator * 100) safely.

    This is a thin wrapper around _safe_divide used by the margin
    calculations, so the caller does not have to repeat "* 100".

    Example:
        _pct(180_700_000_000, 391_000_000_000)  →  46.2  (46.2%)
    """
    result = _safe_divide(numerator, denominator)
    return result * 100 if result is not None else None


# ------------------------------------------------------------
# Income statement
# ------------------------------------------------------------

def _compute_income(df) -> dict:
    """
    Extract and calculate all income statement fields for up to 4
    annual periods.

    Returns a dictionary with:
      - years          : list of year strings, e.g. ["2024","2023","2022"]
      - revenue        : list of raw float values (or None)
      - gross_profit   : list
      - gross_margin   : list of percentages (float, e.g. 46.2)
      - op_income      : list (operating income)
      - op_margin      : list of percentages
      - net_income     : list
      - eps_diluted    : list (per-share earnings)
      - shares_diluted : list (diluted average shares outstanding)
      - revenue_growth : list of % growth rates (length = n_years - 1)
      - acceleration   : string label for revenue growth trend
    """
    if df is None or df.empty:
        return {"error": "Income statement not available."}

    # Cap at 4 annual periods so the terminal table stays readable.
    # df.columns holds the date of each annual period (most recent first).
    n_years = min(len(df.columns), 4)
    years   = [str(col.year) for col in df.columns[:n_years]]

    # Accumulate one value per year for each line item.
    revenues       = []
    gross_profits  = []
    gross_margins  = []
    op_incomes     = []
    op_margins     = []
    net_incomes    = []
    eps_list       = []
    shares_list    = []

    for i in range(n_years):

        rev = _extract_value(df, [
            "Total Revenue", "TotalRevenue", "Revenue",
        ], i)

        gp = _extract_value(df, [
            "Gross Profit", "GrossProfit",
        ], i)

        op = _extract_value(df, [
            "Operating Income", "OperatingIncome",
            "Operating Revenue", "EBIT", "Ebit",
        ], i)

        net = _extract_value(df, [
            "Net Income",
            "NetIncome",
            "Net Income Common Stockholders",
            "Net Income From Continuing Operations",
        ], i)

        # EPS: prefer diluted; fall back to basic if diluted absent.
        eps = _extract_value(df, [
            "Diluted EPS", "DilutedEPS",
            "Diluted Earnings Per Share",
            "Basic EPS", "BasicEPS",
        ], i)

        # Diluted average shares outstanding helps the reader judge
        # whether EPS growth is from earnings growth or buybacks.
        shares = _extract_value(df, [
            "Diluted Average Shares", "DilutedAverageShares",
            "Basic Average Shares", "BasicAverageShares",
            "Weighted Average Diluted Shares",
            "Average Diluted Shares Outstanding",
        ], i)

        revenues.append(rev)
        gross_profits.append(gp)
        gross_margins.append(_pct(gp, rev))
        op_incomes.append(op)
        op_margins.append(_pct(op, rev))
        net_incomes.append(net)
        eps_list.append(eps)
        shares_list.append(shares)

    # ---- Revenue growth ----------------------------------------
    # revenue_growth[i] = percentage change from year[i+1] to year[i]
    # Index 0 = most recent year's growth vs the year before.
    #
    # Example with years ["2024","2023","2022"]:
    #   revenue_growth[0] = (rev_2024 - rev_2023) / rev_2023 * 100
    #   revenue_growth[1] = (rev_2023 - rev_2022) / rev_2022 * 100

    revenue_growth: list[float | None] = []

    for i in range(n_years - 1):
        current = revenues[i]
        prior   = revenues[i + 1]

        if current is not None and prior is not None:
            growth_pct = _safe_divide(current - prior, prior)
            revenue_growth.append(
                growth_pct * 100 if growth_pct is not None else None
            )
        else:
            revenue_growth.append(None)

    # ---- Revenue growth acceleration ---------------------------
    # Compare the most recent annual growth rate with the prior one.
    # We need at least two growth rates (three years of revenue) to
    # draw this conclusion.
    #
    # Threshold of ±1 percentage point avoids flagging noise as a trend.

    acceleration = "Unavailable"

    if (
        len(revenue_growth) >= 2
        and revenue_growth[0] is not None
        and revenue_growth[1] is not None
    ):
        latest   = revenue_growth[0]
        previous = revenue_growth[1]
        diff     = latest - previous

        if diff > 1.0:
            acceleration = "Accelerating"
        elif diff < -1.0:
            acceleration = "Slowing"
        else:
            acceleration = "Broadly stable"

    return {
        "years":          years,
        "revenue":        revenues,
        "gross_profit":   gross_profits,
        "gross_margin":   gross_margins,
        "op_income":      op_incomes,
        "op_margin":      op_margins,
        "net_income":     net_incomes,
        "eps_diluted":    eps_list,
        "shares_diluted": shares_list,
        "revenue_growth": revenue_growth,
        "acceleration":   acceleration,
    }


# ------------------------------------------------------------
# Balance sheet
# ------------------------------------------------------------

def _compute_balance(df) -> dict:
    """
    Extract balance sheet line items and calculate key ratios.

    DEBT-TO-EQUITY SPECIAL CASES:
      Negative equity makes D/E misleading (a company heavily
      funded by debt could show a small positive or negative ratio
      that looks healthy but is not).  We therefore flag rather
      than silently calculate in those cases:
        - equity is None  → N/A (data unavailable)
        - equity == 0     → "Not meaningful (zero equity)"
        - equity < 0      → "Not meaningful (negative equity)"

    CURRENT RATIO:
      current_assets / current_liabilities.  Values below 1.0
      suggest the company may struggle to cover short-term
      obligations with liquid assets.
    """
    if df is None or df.empty:
        return {"error": "Balance sheet not available."}

    cash = _extract_value(df, [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Short Term Investments",
        "Cash",
    ])

    total_debt = _extract_value(df, [
        "Total Debt", "TotalDebt",
        "Long Term Debt", "LongTermDebt",
    ])

    equity = _extract_value(df, [
        "Stockholders Equity",
        "Total Stockholder Equity",
        "Stockholders' Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
        "Equity",
    ])

    current_assets = _extract_value(df, [
        "Current Assets", "Total Current Assets", "CurrentAssets",
    ])

    current_liabilities = _extract_value(df, [
        "Current Liabilities", "Total Current Liabilities", "CurrentLiabilities",
    ])

    retained_earnings = _extract_value(df, [
        "Retained Earnings", "RetainedEarnings",
    ])

    # ---- Debt-to-equity ----------------------------------------
    de_ratio: float | None = None
    de_note:  str   | None = None

    if total_debt is None or equity is None:
        de_note = "N/A"
    elif equity == 0:
        de_note = "Not meaningful (zero equity)"
    elif equity < 0:
        de_note = "Not meaningful (negative equity)"
    else:
        de_ratio = total_debt / equity

    # ---- Current ratio -----------------------------------------
    current_ratio = _safe_divide(current_assets, current_liabilities)

    return {
        "cash":               cash,
        "total_debt":         total_debt,
        "equity":             equity,
        "de_ratio":           de_ratio,   # float, or None if not meaningful
        "de_note":            de_note,    # explanation string, or None
        "current_assets":     current_assets,
        "current_liabilities": current_liabilities,
        "current_ratio":      current_ratio,
        "retained_earnings":  retained_earnings,
    }


# ------------------------------------------------------------
# Cash flow statement
# ------------------------------------------------------------

def _compute_cashflow(df) -> dict:
    """
    Extract operating cash flow, capital expenditure, and derive
    free cash flow.

    CAPEX SIGN CONVENTION — important:
        yfinance typically reports capital expenditure as a NEGATIVE
        number because it is a cash outflow.  For example, Apple
        spending $11B on CapEx may come back as -11_000_000_000.

        We normalise with abs() so CapEx is always a positive number
        representing how much was spent.  Then:

            Free Cash Flow = Operating Cash Flow − CapEx

        Because both are positive amounts, there is no risk of
        double-counting the sign.  If yfinance ever returns CapEx
        as positive (some companies report it that way), abs() is
        still correct — it is a no-op on a positive number.

    FREE CASH FLOW interpretation:
        Positive FCF means the business generated more cash from
        operations than it spent on maintaining and growing its
        physical asset base.  Negative FCF may indicate heavy
        investment or operational challenges.
    """
    if df is None or df.empty:
        return {"error": "Cash flow statement not available."}

    operating_cf = _extract_value(df, [
        "Operating Cash Flow",
        "Total Cash From Operating Activities",
        "Cash Flows From Used In Operating Activities",
        "Net Cash Provided By Operating Activities",
    ])

    # Raw CapEx — may be negative (cash outflow) depending on yfinance
    capex_raw = _extract_value(df, [
        "Capital Expenditure",
        "Capital Expenditures",
        "Purchase Of Property Plant And Equipment",
        "Purchases Of Property And Equipment",
        "Capital Expenditures Reported",
    ])

    # Normalise to a positive amount regardless of reported sign
    capex = abs(capex_raw) if capex_raw is not None else None

    # FCF = Operating CF − CapEx (both positive)
    if operating_cf is not None and capex is not None:
        free_cash_flow = operating_cf - capex
    else:
        free_cash_flow = None

    return {
        "operating_cf":   operating_cf,
        "capex":          capex,          # always positive: amount spent
        "free_cash_flow": free_cash_flow,
    }


# ------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------

def get_financial_statements(ticker_symbol: str) -> dict | None:
    """
    Fetch and compute all three financial statements for a ticker.

    This is the only function that main.py needs to call from this
    module.  It coordinates the three _compute_* helpers and returns
    a single unified dictionary.

    Parameters:
        ticker_symbol (str): e.g. "AAPL" or "JPM"

    Returns:
        A dict with keys:
            "currency_code"   : e.g. "USD"
            "currency_symbol" : e.g. "$"
            "income"          : dict from _compute_income()
            "balance"         : dict from _compute_balance()
            "cashflow"        : dict from _compute_cashflow()
        Returns None if the ticker appears to be invalid.
    """
    ticker = yf.Ticker(ticker_symbol)

    # .info is needed for the reporting currency.
    # We tolerate failure here — currency will fall back to USD.
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    if not info or "symbol" not in info:
        return None

    currency_code, currency_symbol = _get_currency_symbol(info)

    # Retrieve each statement DataFrame.  Wrapped individually so
    # that a missing statement (e.g. ETFs have no income statement)
    # does not prevent the others from loading.
    try:
        income_df = ticker.financials      # Annual income statement
    except Exception:
        income_df = None

    try:
        balance_df = ticker.balance_sheet  # Annual balance sheet
    except Exception:
        balance_df = None

    try:
        cashflow_df = ticker.cashflow      # Annual cash flow
    except Exception:
        cashflow_df = None

    return {
        "currency_code":   currency_code,
        "currency_symbol": currency_symbol,
        "income":          _compute_income(income_df),
        "balance":         _compute_balance(balance_df),
        "cashflow":        _compute_cashflow(cashflow_df),
    }
