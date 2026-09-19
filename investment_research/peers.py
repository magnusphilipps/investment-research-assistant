"""
peers.py — Peer Comparison Feature (Feature 7)

Responsibilities:
- Maintain a simple editable PEERS mapping
- Fetch required metrics for a target and its peers
- Reuse get_financial_statements() and get_ratios() from financials.py
- Return a structured result (pandas DataFrame + summary) for display

This file is intentionally small and focused so the display logic
remains in display.py and calculations remain in financials.py.
"""

from __future__ import annotations

import math
from typing import List, Dict, Any

import pandas as pd
import yfinance as yf

from . import fetcher, gemini_provider
from .financials import get_financial_statements, get_ratios

# Feature 7 treats a peer as usable only when at least 4 of the core
# comparison metrics are available; otherwise the comparison is too thin.
PEER_DISCOVERY_MIN_METRICS = 4
PEER_DISCOVERY_TARGET_COUNT = 5
PEER_DISCOVERY_RETURN_COUNT = 3


# Manually configured peer mapping. Edit as needed.
# Keys are the primary ticker (uppercase); values are lists of three peers.
PEERS: Dict[str, List[str]] = {
    "NVDA": ["AMD", "AVGO", "INTC"],
    "AAPL": ["MSFT", "GOOGL", "AMZN"],
    "JPM":  ["BAC", "WFC", "C"],
    "NFLX": ["DIS", "CMCSA", "PARA"],
    # OKLO intentionally omitted so the app demonstrates the "no peers" path
}


def _normalise_ticker(value: Any) -> str | None:
    """Return a cleaned uppercase ticker, or None when it is empty/invalid."""
    if value is None:
        return None
    ticker = str(value).strip().upper()
    return ticker if ticker else None


def _ticker_exists(ticker: str) -> bool:
    """Check whether a ticker resolves with the existing provider data."""
    try:
        info = (yf.Ticker(ticker).info or {})
    except Exception:
        return False
    return bool(info.get("symbol") or info.get("shortName") or info.get("longName"))


def _is_valid_metric_value(value: Any, *, metric_name: str | None = None) -> bool:
    """Match the Feature 7 rules for usable metric values."""
    if value is None:
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(numeric):
        return False
    if metric_name in {"P/E", "Forward P/E", "EV/EBITDA"} and numeric < 0:
        return False
    return True


def _peer_metric_count(ticker: str) -> int:
    """Count Feature 7 metrics available for a candidate peer."""
    try:
        fin = get_financial_statements(ticker)
    except Exception:
        return 0
    if not fin:
        return 0

    count = 0
    income = fin.get("income") or {}
    revenue_growth = income.get("revenue_growth") or []
    if revenue_growth and _is_valid_metric_value(revenue_growth[0], metric_name="Revenue Growth"):
        count += 1

    try:
        ratios = get_ratios(ticker, fin)
    except Exception:
        ratios = {}

    prof = ratios.get("profitability", {})
    strength = ratios.get("strength", {})
    val = ratios.get("valuation", {})

    for metric_name, value in {
        "Operating Margin": prof.get("op_margin") if not _is_financial_company(ticker) else None,
        "ROE": prof.get("roe"),
        "Debt/Equity": strength.get("de_ratio"),
        "P/E": val.get("trailing_pe"),
        "Forward P/E": val.get("forward_pe"),
        "EV/EBITDA": val.get("ev_ebitda"),
    }.items():
        if _is_valid_metric_value(value, metric_name=metric_name):
            count += 1
    return count


def _discover_peer_candidates(ticker: str) -> list[str]:
    """Use Gemini to propose peers and validate them with the existing Feature 7 metrics."""
    target = _normalise_ticker(ticker)
    if not target:
        return []

    try:
        stock_info = fetcher.get_stock_info(target)
    except Exception:
        stock_info = None
    if not isinstance(stock_info, dict):
        return []

    context = {
        "ticker": target,
        "company_name": stock_info.get("name"),
        "sector": stock_info.get("sector"),
        "industry": stock_info.get("industry"),
        "country": stock_info.get("country"),
        "description": stock_info.get("description"),
        "research_focus": {
            "sector": stock_info.get("sector"),
            "industry": stock_info.get("industry"),
            "business_summary": (stock_info.get("description") or "")[:1200],
        },
    }

    try:
        discovery = gemini_provider.generate_peer_candidates(context)
    except Exception:
        return []
    if not isinstance(discovery, dict) or discovery.get("status") != "ok":
        return []

    candidates = discovery.get("peers", [])
    if not isinstance(candidates, list):
        return []

    ranked: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        candidate_ticker = _normalise_ticker(item.get("ticker"))
        if not candidate_ticker or candidate_ticker == target:
            continue
        if candidate_ticker in seen:
            continue
        if not _ticker_exists(candidate_ticker):
            continue
        metric_count = _peer_metric_count(candidate_ticker)
        if metric_count < PEER_DISCOVERY_MIN_METRICS:
            continue
        seen.add(candidate_ticker)
        ranked.append((metric_count, index, candidate_ticker))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [ticker for _, _, ticker in ranked[:PEER_DISCOVERY_RETURN_COUNT]]


def get_peers(ticker: str) -> List[str] | None:
    """Return the best dynamic peer set, or the configured manual map as fallback."""
    target = _normalise_ticker(ticker)
    if not target:
        return None

    dynamic_peers = _discover_peer_candidates(target)
    if dynamic_peers:
        return dynamic_peers

    configured = PEERS.get(target)
    if configured:
        return list(configured)
    return None


def _safe_first(lst: list | None) -> float | None:
    """Return the first element of a list or None if the list is empty.

    This mirrors small helper behaviour in other modules so callers
    don't crash when a list is missing or empty.
    """
    if not lst:
        return None
    return lst[0]


def fetch_peer_comparison(ticker: str) -> Dict[str, Any]:
    """Build a peer comparison for `ticker` using the configured peers.

    The result is a dict with keys:
      - available (bool): whether a configured peer group exists
      - message (str): when available is False, a human message
      - tickers (list): ordered list [target, peer1, peer2, peer3]
      - df (pandas.DataFrame): rows=metrics, columns=tickers (raw numeric/None)
      - summary (list[str]): 1-2 factual sentences derived from the df

    The DataFrame uses the following row labels:
      "Revenue Growth", "Operating Margin", "ROE", "Debt/Equity",
      "P/E", "Forward P/E", "EV/EBITDA"

    Calculations reuse get_financial_statements() and get_ratios().
    Missing values are left as None so the display layer can render "N/A".
    """
    peers = get_peers(ticker)
    if not peers:
        return {"available": False, "message": "Peer comparison unavailable for this company."}

    tickers = [ticker] + peers

    # Prepare containers for each metric
    rows = {
        "Revenue Growth": [],    # percent (e.g. 55.2)
        "Operating Margin": [],  # percent
        "ROE": [],               # percent
        "Debt/Equity": [],       # ratio (float) or None
        "P/E": [],               # trailing P/E
        "Forward P/E": [],
        "EV/EBITDA": [],
    }

    for t in tickers:
        try:
            fin = get_financial_statements(t)
        except Exception:
            fin = None

        # Revenue growth: most recent annual YoY from income statement
        rev_growth = None
        if fin and isinstance(fin.get("income"), dict):
            inc = fin.get("income", {})
            rg = inc.get("revenue_growth")
            if rg and len(rg) > 0 and rg[0] is not None:
                rev_growth = rg[0]
        rows["Revenue Growth"].append(rev_growth)

        # Ratios and valuation (one call reuses existing logic)
        op_margin = None
        roe = None
        de_ratio = None
        trailing_pe = None
        forward_pe = None
        ev_ebitda = None

        if fin:
            try:
                ratios = get_ratios(t, fin)
            except Exception:
                ratios = {}

            prof = ratios.get("profitability", {})
            strength = ratios.get("strength", {})
            val = ratios.get("valuation", {})

            # Conventional operating margin is not meaningful for many banks,
            # so Feature 7 suppresses it for financial companies rather than
            # comparing a misleading number.
            if _is_financial_company(t):
                op_margin = None
            else:
                op_margin = prof.get("op_margin")

            roe = prof.get("roe")
            de_ratio = strength.get("de_ratio")
            # trailing/forward P/E and EV/EBITDA come from valuation.
            # Negative valuation multiples are not economically meaningful for
            # this peer-comparison display, so we treat them as unavailable.
            trailing_pe = val.get("trailing_pe")
            forward_pe = val.get("forward_pe")
            ev_ebitda = val.get("ev_ebitda")
            for metric_name, value in {
                "P/E": trailing_pe,
                "Forward P/E": forward_pe,
                "EV/EBITDA": ev_ebitda,
            }.items():
                if value is None:
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(numeric) or numeric < 0:
                    if metric_name == "P/E":
                        trailing_pe = None
                    elif metric_name == "Forward P/E":
                        forward_pe = None
                    else:
                        ev_ebitda = None

        rows["Operating Margin"].append(op_margin)
        rows["ROE"].append(roe)
        rows["Debt/Equity"].append(de_ratio)
        rows["P/E"].append(trailing_pe)
        rows["Forward P/E"].append(forward_pe)
        rows["EV/EBITDA"].append(ev_ebitda)

    # Build DataFrame for easier downstream processing
    df = pd.DataFrame(rows, index=tickers).T
    # The DataFrame index is the metric names, columns are tickers

    summary = _build_factual_summary(ticker, df)

    return {
        "available": True,
        "tickers": tickers,
        "df": df,
        "summary": summary,
    }


def _is_financial_company(ticker: str) -> bool:
    """Return True when a ticker is a bank or other financial institution.

    This is intentionally scoped to Feature 7 only. Conventional operating
    margin is not a meaningful ratio for many banks, so we suppress it rather
    than compare a misleading value.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}

    sector = str(info.get("sector") or "").lower()
    industry = str(info.get("industry") or "").lower()
    text = f"{sector} {industry}".strip()

    financial_keywords = (
        "bank", "banks", "financial", "finance", "insurance",
        "asset management", "brokerage", "credit", "mortgage"
    )
    return any(keyword in text for keyword in financial_keywords)


def _build_factual_summary(target: str, df: pd.DataFrame) -> List[str]:
    """Generate 1–2 factual sentences from the comparison DataFrame.

    The summary is always written from the perspective of the target ticker,
    and it ignores any peers that do not have usable values for a specific
    metric. This keeps the wording accurate when some peer data is missing.
    """

    def _usable_metric_values(metric: str, series: pd.Series) -> list[tuple[str, float]]:
        peers = [c for c in series.index if c != target]
        usable: list[tuple[str, float]] = []
        for peer in peers:
            value = series.get(peer)
            if pd.isna(value):
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(numeric):
                continue
            if metric in {"P/E", "Forward P/E", "EV/EBITDA"} and numeric < 0:
                continue
            usable.append((peer, numeric))
        return usable

    def _peer_phrase(metric: str, count: int, total: int, all_valid: bool) -> str:
        if all_valid:
            if total == 1:
                return "the only selected peer"
            if count == total:
                return f"all {total} selected peers"
            if total == 2 and count == 2:
                return "both selected peers"
            return f"{count} of its {total} selected peers"

        metric_name = f"{metric.lower()} data"
        if total == 1:
            return f"the only peer with available {metric_name}"
        if count == total:
            return f"all {total} peers with available {metric_name}"
        if total == 2 and count == 2:
            return f"both peers with available {metric_name}"
        return f"{count} of the {total} peers with available {metric_name}"

    def _metric_text(metric: str, series: pd.Series, target_value: float) -> str | None:
        """Build a target-perspective clause for a single metric."""
        valid_peers = _usable_metric_values(metric, series)
        if not valid_peers:
            return None

        total = len(valid_peers)
        selected_total = len([c for c in series.index if c != target])
        lower_count = sum(1 for _, value in valid_peers if value < target_value)
        higher_count = sum(1 for _, value in valid_peers if value > target_value)

        if lower_count == total:
            return f"{target} has the highest {metric.lower()} among the four companies."
        if higher_count == total:
            return f"{target} has the lowest {metric.lower()} in this peer group."

        if total == 1:
            if lower_count == 1:
                return f"{target} has higher {metric.lower()} than the only peer with available {metric.lower()} data."
            if higher_count == 1:
                return f"{target} has lower {metric.lower()} than the only peer with available {metric.lower()} data."

        if lower_count > 0:
            if total == 2 and lower_count == 2:
                phrase = _peer_phrase(metric, lower_count, total, total == selected_total)
                return f"{target} has higher {metric.lower()} than {phrase}."
            phrase = _peer_phrase(metric, lower_count, total, total == selected_total)
            return f"{target} has higher {metric.lower()} than {phrase}."
        if higher_count > 0:
            if total == 2 and higher_count == 2:
                phrase = _peer_phrase(metric, higher_count, total, total == selected_total)
                return f"{target} has lower {metric.lower()} than {phrase}."
            phrase = _peer_phrase(metric, higher_count, total, total == selected_total)
            return f"{target} has lower {metric.lower()} than {phrase}."

        return None

    # Revenue growth and operating margin are the only metrics we combine into
    # one sentence; we omit operating margin if the company is a bank.
    rg_series = pd.to_numeric(df.loc["Revenue Growth"], errors="coerce")
    rg_target_value = rg_series.get(target)
    rg_sentence = None
    if not pd.isna(rg_target_value):
        rg_sentence = _metric_text("Revenue Growth", rg_series, float(rg_target_value))

    om_series = pd.to_numeric(df.loc["Operating Margin"], errors="coerce")
    om_target_value = om_series.get(target)
    om_sentence = None
    if not pd.isna(om_target_value) and not _is_financial_company(target):
        om_sentence = _metric_text("Operating Margin", om_series, float(om_target_value))

    sentences: List[str] = []

    if rg_sentence and om_sentence:
        if "highest" in rg_sentence and "highest" in om_sentence:
            sentences.append(f"{target} has the highest revenue growth and operating margin among the four companies.")
        elif "lowest" in rg_sentence and "lowest" in om_sentence:
            sentences.append(f"{target} has the lowest revenue growth and operating margin in this peer group.")
        else:
            rg_text = rg_sentence.rstrip('.')
            om_text = om_sentence.rstrip('.')
            om_tail = om_text
            prefix = f"{target} has "
            if om_text.lower().startswith(prefix.lower()):
                om_tail = om_text[len(prefix):]
            if om_tail.lower().startswith(("higher ", "lower ")):
                om_tail = "a " + om_tail
            sentences.append(f"{rg_text} and {om_tail}.")
    elif rg_sentence:
        sentences.append(rg_sentence)
    elif om_sentence:
        sentences.append(om_sentence)

    pe_series = pd.to_numeric(df.loc["P/E"], errors="coerce")
    if not pe_series.isna().all():
        target_pe = pe_series.get(target)
        if not pd.isna(target_pe) and target_pe >= 0:
            peers_list = [c for c in pe_series.index if c != target]
            valid_peers = [p for p in peers_list if p in pe_series.index and not pd.isna(pe_series.get(p)) and float(pe_series.get(p)) >= 0]
            if valid_peers:
                below = sum(1 for p in valid_peers if float(pe_series.get(p)) < float(target_pe))
                above = sum(1 for p in valid_peers if float(pe_series.get(p)) > float(target_pe))
                total = len(valid_peers)
                selected_total = len(peers_list)
                subject = "Its P/E" if sentences else f"{target}'s P/E"

                if below == total:
                    phrase = _peer_phrase("P/E", total, total, total == selected_total)
                    if total == 1:
                        sentences.append(f"{subject} is higher than the only peer with available P/E data.")
                    elif total == 2:
                        sentences.append(f"{subject} is higher than both peers with available P/E data.")
                    else:
                        sentences.append(f"{subject} is higher than all {total} selected peers.")
                elif above == total:
                    if total == 1:
                        sentences.append(f"{subject} is lower than the only peer with available P/E data.")
                    elif total == 2:
                        sentences.append(f"{subject} is lower than both peers with available P/E data.")
                    else:
                        sentences.append(f"{subject} is lower than all {total} selected peers.")
                elif total == 1:
                    if below == 1:
                        sentences.append(f"{subject} is higher than the only peer with available P/E data.")
                    elif above == 1:
                        sentences.append(f"{subject} is lower than the only peer with available P/E data.")
                else:
                    if below > 0:
                        selected_phrase = _peer_phrase("P/E", below, total, total == selected_total)
                        sentences.append(f"{subject} is higher than {selected_phrase}.")
                    elif above > 0:
                        selected_phrase = _peer_phrase("P/E", above, total, total == selected_total)
                        sentences.append(f"{subject} is lower than {selected_phrase}.")

    if not sentences:
        return ["Insufficient data to produce a factual peer summary."]

    return sentences[:2]
