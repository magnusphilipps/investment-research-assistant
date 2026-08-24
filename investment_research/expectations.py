"""
investment_research/expectations.py

Feature 6 — Analyst Expectations & Forward Outlook

This module fetches analyst price targets, recommendation counts, and
(rewhere available) forward revenue estimates from yfinance. The code is
written defensively: if Yahoo/ yfinance does not provide a value, the
functions return None for numeric values and the display layer prints "N/A".

The module is intentionally conservative: it does not invent missing data.
It returns a single structured dictionary which the display layer formats.

Docstrings and concise comments explain the inputs, outputs and why helper
functions exist — helpful for someone learning Python and pandas.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import math
import yfinance as yf
import pandas as pd


def _safe_number(value: Any) -> Optional[float]:
    """
    Convert a value to float when possible, returning None for missing / NaN.

    This helper centralises the small but important defensive pattern of
    treating missing numeric data as None (so the display layer can print
    "N/A") rather than converting to zero.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except Exception:
        return None
    if math.isnan(f):
        return None
    return f


def _format_pct(raw: Optional[float]) -> Optional[float]:
    """
    Return a plain fractional percent (e.g. 0.114 for +11.4%) as a float.

    The display layer is responsible for rendering +/− and percent signs.
    """
    return _safe_number(raw)


def get_analyst_expectations(ticker_symbol: str) -> Dict[str, Any]:
    """
    Top-level function returning analyst expectations for a ticker.

    Parameters:
        ticker_symbol: Upper- or lower-case ticker symbol (e.g. "AAPL")

    Returns:
        A dictionary with keys:
          - price_targets: dict with current_price, avg, median, high, low,
                           analysts, implied_upside (fraction) — values or None
          - recommendations: dict with counts (Strong Buy/Buy/Hold/Sell/Strong Sell)
                             and consensus (string) or None
          - revenue_estimates: dict with current_year and next_year entries
                                each of which is {'revenue': float|None, 'growth': float|None}
          - summary: list[str] of short factual summary sentences (may be empty)

    Notes:
        This function attempts several common yfinance fields and DataFrame
        structures but never assumes the data is present. When data is not
        available it returns None for the numeric fields — the display layer
        will print "N/A".
    """

    ticker = yf.Ticker(ticker_symbol)

    # --- info dictionary: lightweight single-call snapshot -------------
    info = getattr(ticker, "info", {}) or {}

    # Current share price: try a couple of common keys
    current_price = (
        _safe_number(info.get("currentPrice"))
        or _safe_number(info.get("regularMarketPrice"))
    )

    # Price target fields: different yfinance versions / responses may
    # name these differently — check a small set of likely keys.
    avg_target = (
        _safe_number(info.get("targetMeanPrice"))
        or _safe_number(info.get("targetAveragePrice"))
    )
    median_target = _safe_number(info.get("targetMedianPrice"))
    high_target = _safe_number(info.get("targetHighPrice"))
    low_target = _safe_number(info.get("targetLowPrice"))

    # Number of analysts (key names vary across yfinance versions)
    analysts = (
        info.get("numberOfAnalystOpinions")
        or info.get("numberOfAnalysts")
        or info.get("analystOpinions")
    )
    try:
        analysts = int(analysts) if analysts is not None else None
    except Exception:
        analysts = None

    implied_upside = None
    if avg_target is not None and current_price is not None and current_price != 0:
        implied_upside = (avg_target / current_price) - 1

    price_targets = {
        "current_price": current_price,
        "average_target": avg_target,
        "median_target": median_target,
        "high_target": high_target,
        "low_target": low_target,
        "analysts": analysts,
        "implied_upside": implied_upside,
    }

    # --- Recommendations: try ticker.recommendations DataFrame if present ---
    recommendations = {k: None for k in ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")}
    consensus = None

    recs_df = getattr(ticker, "recommendations", None)
    try:
        if isinstance(recs_df, pd.DataFrame) and not recs_df.empty:
            # --- Preferred path: structured count columns are available ---
            # Example NVDA columns: strongBuy, buy, hold, sell, strongSell
            cols_lower = {c.lower(): c for c in recs_df.columns}

            # Helper to find a column name matching an expected token
            def _find_col_token(token: str) -> Optional[str]:
                token = token.lower()
                # Prefer exact column name matches first (e.g. 'buy' -> 'buy')
                if token in cols_lower:
                    return cols_lower[token]
                # Try a simple normalization: remove underscores and try again
                alt = token.replace("_", "")
                if alt in cols_lower:
                    return cols_lower[alt]
                # No suitable match found
                return None

            structured_cols = {
                "Strong Buy": _find_col_token("strongbuy") or _find_col_token("strong_buy"),
                "Buy": _find_col_token("buy"),
                "Hold": _find_col_token("hold"),
                "Sell": _find_col_token("sell"),
                "Strong Sell": _find_col_token("strongsell") or _find_col_token("strong_sell"),
            }

            if any(structured_cols.values()):
                # Prefer the '0m' row (current month/period) when present
                idx_labels = [str(i) for i in recs_df.index]
                row_label = None
                if "0m" in idx_labels:
                    row_label = "0m"
                else:
                    # Try any label that starts with '0'
                    for lbl in idx_labels:
                        if lbl.startswith("0"):
                            row_label = lbl
                            break
                # Fallback to the first row
                if row_label is None:
                    row = recs_df.iloc[0]
                else:
                    # Use .loc with the original index (may be string or other type)
                    try:
                        row = recs_df.loc[row_label]
                    except Exception:
                        row = recs_df.iloc[0]

                # Extract integer counts when possible
                extracted = {}
                for key, colname in structured_cols.items():
                    if colname is not None and colname in recs_df.columns:
                        try:
                            val = row[colname]
                            if pd.isna(val):
                                extracted[key] = None
                            else:
                                extracted[key] = int(val)
                        except Exception:
                            extracted[key] = None
                    else:
                        extracted[key] = None

                recommendations = extracted

                total_counts = sum(v for v in recommendations.values() if isinstance(v, int))
                if total_counts > 0:
                    consensus = max(recommendations.items(), key=lambda kv: (kv[1] or 0))[0]
            else:
                # --- Fallback: text-based parsing of any string column ---
                # Find any string column to inspect textual grades
                text_col = None
                for c in recs_df.columns:
                    if pd.api.types.is_string_dtype(recs_df[c]):
                        text_col = c
                        break

                if text_col is not None:
                    # Avoid regex-based Series.str.contains to prevent pandas warnings.
                    vals = recs_df[text_col].dropna().astype(str).str.strip().str.lower()
                    counts = {"Strong Buy": 0, "Buy": 0, "Hold": 0, "Sell": 0, "Strong Sell": 0}
                    for s in vals:
                        if "strong buy" in s:
                            counts["Strong Buy"] += 1
                        elif "strong sell" in s:
                            counts["Strong Sell"] += 1
                        elif "buy" in s and "strong" not in s:
                            counts["Buy"] += 1
                        elif "sell" in s and "strong" not in s:
                            counts["Sell"] += 1
                        elif "hold" in s:
                            counts["Hold"] += 1
                    recommendations = counts
                    total_counts = sum(counts.values())
                    if total_counts > 0:
                        consensus = max(counts.items(), key=lambda kv: kv[1])[0]
    except Exception:
        # Any parsing error should not raise — leave recommendations as None/N/A
        recommendations = {k: None for k in recommendations}
        consensus = None

    recs_struct = {"counts": recommendations, "consensus": consensus}

    # --- Revenue estimates: yfinance exposes different structures.
    # We try a few locations, recognising this will often be unavailable.
    revenue_estimates = {"current_year": {"revenue": None, "growth": None}, "next_year": {"revenue": None, "growth": None}}

    # 1) Some yfinance variants include an 'earningsTrend' dict in info
    et = info.get("earningsTrend") or {}
    try:
        if isinstance(et, dict):
            # 'trend' may be a list of dicts containing 'period', 'revenue' fields
            trend = et.get("trend") or []
            if isinstance(trend, list) and len(trend) > 0:
                # Attempt to find current and next fiscal year entries by period name
                for entry in trend:
                    period = entry.get("period")
                    rev = _safe_number(entry.get("revenue"))
                    growth = _safe_number(entry.get("revenueGrowth")) or _safe_number(entry.get("growth"))
                    if period and "current" in period.lower():
                        revenue_estimates["current_year"]["revenue"] = rev
                        revenue_estimates["current_year"]["growth"] = growth
                    elif period and ("next" in period.lower() or "1y" in period.lower()):
                        revenue_estimates["next_year"]["revenue"] = rev
                        revenue_estimates["next_year"]["growth"] = growth
    except Exception:
        # Ignore parsing errors
        pass

    # 2) Some yfinance exposes an attribute `revenue_estimate` as a DataFrame
    #    with rows labelled like '0q', '+1q', '0y' (current fiscal year) and '+1y' (next year).
    #    When present, prefer these structured estimates and access rows by index label.
    try:
        revenue_df = getattr(ticker, "revenue_estimate", None)
        if isinstance(revenue_df, pd.DataFrame) and not revenue_df.empty:
            # Helper to safely get a row by exact index label (case-insensitive fallback).
            def _safe_get_row(label: str):
                # Direct .loc lookup when possible
                try:
                    if label in revenue_df.index:
                        return revenue_df.loc[label]
                except Exception:
                    # ignore and try string-based matching below
                    pass

                # Fallback: match by stringified index values (case-insensitive)
                target = label.lower()
                for idx_val in revenue_df.index:
                    try:
                        if str(idx_val).lower() == target:
                            return revenue_df.loc[idx_val]
                    except Exception:
                        continue
                return None

            # Current-year and next-year labels to try (in order)
            row_current = _safe_get_row("0y")
            row_next = _safe_get_row("+1y")

            # Extract avg and growth using the safe-number helper
            if row_current is not None:
                try:
                    cy_avg = _safe_number(row_current.get("avg") if hasattr(row_current, "get") else row_current["avg"] if "avg" in row_current else None)
                except Exception:
                    cy_avg = None
                try:
                    cy_growth = _safe_number(row_current.get("growth") if hasattr(row_current, "get") else row_current["growth"] if "growth" in row_current else None)
                except Exception:
                    cy_growth = None
                revenue_estimates["current_year"]["revenue"] = cy_avg
                revenue_estimates["current_year"]["growth"] = cy_growth

            if row_next is not None:
                try:
                    ny_avg = _safe_number(row_next.get("avg") if hasattr(row_next, "get") else row_next["avg"] if "avg" in row_next else None)
                except Exception:
                    ny_avg = None
                try:
                    ny_growth = _safe_number(row_next.get("growth") if hasattr(row_next, "get") else row_next["growth"] if "growth" in row_next else None)
                except Exception:
                    ny_growth = None
                revenue_estimates["next_year"]["revenue"] = ny_avg
                revenue_estimates["next_year"]["growth"] = ny_growth
    except Exception:
        # Ignore parsing errors — leave revenue_estimates as previously found/None
        pass

    # --- Short factual summary (rule-based) -----------------------
    summary_lines: list[str] = []

    # Revenue summary
    cy_rev = revenue_estimates["current_year"]["revenue"]
    ny_rev = revenue_estimates["next_year"]["revenue"]
    cy_g = revenue_estimates["current_year"]["growth"]
    ny_g = revenue_estimates["next_year"]["growth"]

    if cy_rev is not None or ny_rev is not None or cy_g is not None or ny_g is not None:
        # If any forward revenue number exists, try to state a factual summary
        if ny_rev is not None and cy_rev is not None and cy_rev != 0:
            # Compute growth between current and next year if both available
            growth_pct = None
            try:
                growth_pct = (ny_rev / cy_rev) - 1
            except Exception:
                growth_pct = None
            if growth_pct is not None:
                # Use natural factual wording depending on sign
                eps = 0.001  # threshold (~0.1%) to treat as "broadly flat"
                if abs(growth_pct) < eps:
                    summary_lines.append("Analysts currently expect revenue to remain broadly flat next year.")
                elif growth_pct > 0:
                    summary_lines.append(f"Analysts currently expect revenue to grow by {growth_pct:.1%} next year.")
                else:
                    summary_lines.append(f"Analysts currently expect revenue to decline by {abs(growth_pct):.1%} next year.")
        elif ny_g is not None:
            # Use analyst-provided growth if available — render with natural wording
            eps = 0.001
            if abs(ny_g) < eps:
                summary_lines.append("Analysts currently expect revenue to remain broadly flat next year.")
            elif ny_g > 0:
                summary_lines.append(f"Analysts currently expect revenue to grow by {ny_g:.1%} next year.")
            else:
                summary_lines.append(f"Analysts currently expect revenue to decline by {abs(ny_g):.1%} next year.")
    else:
        # No revenue estimates available
        summary_lines.append("Analyst coverage is limited; forward revenue estimates are unavailable.")

    # Price target summary
    if price_targets["average_target"] is not None and price_targets["current_price"] is not None:
        implied = price_targets["implied_upside"]
        if implied is not None:
            sign = "+" if implied >= 0 else ""
            summary_lines.append(f"The average analyst price target is {sign}{implied:.1%} relative to the current share price.")
    else:
        # If no meaningful price target data
        if price_targets["average_target"] is None:
            summary_lines.append("Average analyst price target is unavailable.")

    # Recommendation coverage summary
    total_recs = sum(v for v in recommendations.values() if isinstance(v, int))
    if total_recs == 0:
        summary_lines.append("Analyst recommendations are unavailable or limited.")

    result = {
        "price_targets": price_targets,
        "recommendations": recs_struct,
        "revenue_estimates": revenue_estimates,
        "summary": summary_lines,
    }

    return result
