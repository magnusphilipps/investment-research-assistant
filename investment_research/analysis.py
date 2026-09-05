"""
analysis.py — Provider-neutral Feature 9 orchestration.

This module turns the structured results from Features 1–8 into a compact
JSON-friendly evidence package. It does not fetch financial data and does not
know how Gemini (or any future provider) talks to its API.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from . import gemini_provider


def _json_safe(value: Any) -> Any:
    """Convert common Python/pandas values into safe JSON-style values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    # pandas and NumPy scalar values commonly provide ``item()``.
    if hasattr(value, "item") and not isinstance(value, (dict, list, tuple)):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass

    try:
        missing = value is not None and value.__class__.__name__ == "NAType"
        if missing:
            return None
    except Exception:
        pass

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    return str(value)


def _subdict(value: Any, key: str) -> dict[str, Any]:
    """Read a nested dictionary without turning missing data into fake values."""
    if not isinstance(value, dict):
        return {}
    child = value.get(key)
    return child if isinstance(child, dict) else {}


def _compact_performance(performance: Any) -> dict[str, Any]:
    """Keep only the useful Feature 5 evidence, excluding retrieval metadata."""
    if not isinstance(performance, dict):
        return {}
    return _json_safe({
        "returns": performance.get("returns", {}),
        "range": performance.get("range", {}),
        "benchmark": performance.get("benchmark", {}),
        "latest_date": performance.get("latest_date"),
    })


def _compact_peers(peers: Any) -> dict[str, Any]:
    """Convert the Feature 7 DataFrame into compact nested dictionaries."""
    if not isinstance(peers, dict):
        return {}

    compact = {
        "available": peers.get("available"),
        "tickers": peers.get("tickers", []),
        "summary": peers.get("summary", []),
        "metrics": {},
    }

    dataframe = peers.get("df")
    if dataframe is not None and hasattr(dataframe, "to_dict"):
        try:
            compact["metrics"] = dataframe.to_dict(orient="index")
        except (TypeError, ValueError):
            compact["metrics"] = {}

    return _json_safe(compact)


def _compact_news(news: Any) -> dict[str, Any]:
    """Keep only the filtered Feature 8 article fields relevant to analysis."""
    if not isinstance(news, dict):
        return {"status": "unavailable", "articles": []}

    articles = news.get("articles", [])
    if not isinstance(articles, list):
        articles = []

    compact_articles = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        compact_articles.append({
            "title": article.get("title"),
            "source": article.get("source"),
            "published_at": article.get("published_at"),
            "description": article.get("description"),
            "url": article.get("url"),
        })

    return _json_safe({
        "status": news.get("status"),
        "articles": compact_articles,
    })


def build_analysis_context(
    ticker: str,
    stock_info: dict | None,
    financials: dict | None,
    ratios: dict | None,
    performance: dict | None,
    expectations: dict | None,
    peers: dict | None,
    news: dict | None,
) -> dict[str, Any]:
    """
    Build the compact evidence package supplied to the AI provider.

    Missing values remain ``None`` or are omitted from an unavailable section.
    In particular, this function never turns missing data into zero or the
    string ``"N/A"``.
    """
    stock_info = stock_info if isinstance(stock_info, dict) else {}
    financials = financials if isinstance(financials, dict) else {}
    ratios = ratios if isinstance(ratios, dict) else {}
    expectations = expectations if isinstance(expectations, dict) else {}

    income = _subdict(financials, "income")
    balance = _subdict(financials, "balance")
    cashflow = _subdict(financials, "cashflow")

    context = {
        "company": {
            "ticker": ticker.upper(),
            "name": stock_info.get("name"),
            "sector": stock_info.get("sector"),
            "industry": stock_info.get("industry"),
            "country": stock_info.get("country"),
            "description": stock_info.get("description"),
            "current_price": stock_info.get("price"),
            "market_cap": stock_info.get("market_cap"),
        },
        "financial_performance": {
            "currency": financials.get("currency_code"),
            "years": income.get("years", []),
            "revenue": income.get("revenue", []),
            "revenue_growth": income.get("revenue_growth", []),
            "gross_profit": income.get("gross_profit", []),
            "gross_margin": income.get("gross_margin", []),
            "operating_income": income.get("op_income", []),
            "operating_margin": income.get("op_margin", []),
            "net_income": income.get("net_income", []),
            "eps_diluted": income.get("eps_diluted", []),
            "growth_trend": income.get("acceleration"),
        },
        "financial_position": {
            "cash": balance.get("cash"),
            "total_debt": balance.get("total_debt"),
            "equity": balance.get("equity"),
            "current_assets": balance.get("current_assets"),
            "current_liabilities": balance.get("current_liabilities"),
            "current_ratio": balance.get("current_ratio"),
            "debt_to_equity": balance.get("de_ratio"),
            "debt_to_equity_note": balance.get("de_note"),
            "retained_earnings": balance.get("retained_earnings"),
            "operating_cash_flow": cashflow.get("operating_cf"),
            "capital_expenditure": cashflow.get("capex"),
            "free_cash_flow": cashflow.get("free_cash_flow"),
        },
        "valuation": _json_safe(_subdict(ratios, "valuation")),
        "share_price_and_expectations": {
            "performance": _compact_performance(performance),
            "analyst_expectations": _json_safe(expectations),
        },
        "peer_positioning": _compact_peers(peers),
        "recent_news": _compact_news(news),
    }
    return _json_safe(context)


def get_ai_analysis(context: dict[str, Any]) -> dict[str, Any]:
    """Request analysis through the currently selected provider."""
    return gemini_provider.generate_analysis(context)