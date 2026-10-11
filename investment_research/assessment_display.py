"""Display-safe helpers for the Streamlit stock assessment dashboard."""

from __future__ import annotations

import math
from typing import Any

from .display import format_market_price


ASSESSMENT_INDICATORS = (
    ("valuation", "Valuation"),
    ("financial_quality", "Financial Quality"),
    ("growth", "Growth"),
    ("risk", "Risk"),
    ("volatility", "Volatility"),
    ("market_environment", "Market Environment"),
    ("competitive_position", "Competitive Position"),
    ("expectations", "Expectations"),
)

_POSITIVE_LABELS = {"positive", "strong", "favourable", "favorable", "cheap", "low"}
_NEUTRAL_LABELS = {"neutral", "moderate", "fair", "medium"}
_CAUTION_LABELS = {
    "negative",
    "weak",
    "unfavourable",
    "unfavorable",
    "expensive",
    "high",
}


def get_label_style(label: str) -> str:
    """Map an assessment label to a non-recommendation visual state."""
    normalized = label.strip().casefold()
    if normalized == "n/a":
        return "muted"
    if normalized in _POSITIVE_LABELS:
        return "positive"
    if normalized in _CAUTION_LABELS:
        return "caution"
    if normalized in _NEUTRAL_LABELS:
        return "neutral"
    return "neutral"


def get_indicator_display(
    report: Any,
    indicator_key: str,
    indicator_name: str,
) -> dict[str, str]:
    """Extract only an indicator's name, label, first driver, and visual state."""
    assessment = report.get("assessment") if isinstance(report, dict) else None
    indicators = assessment.get("indicators") if isinstance(assessment, dict) else None
    indicator = indicators.get(indicator_key) if isinstance(indicators, dict) else None
    if not isinstance(indicator, dict):
        indicator = {}

    raw_label = indicator.get("label")
    label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else "N/A"

    raw_drivers = indicator.get("drivers")
    drivers = raw_drivers if isinstance(raw_drivers, list) else []
    driver = next(
        (value.strip() for value in drivers if isinstance(value, str) and value.strip()),
        "",
    )

    return {
        "name": indicator_name,
        "label": label,
        "driver": driver,
        "style": get_label_style(label),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _section(report: Any, *path: str) -> dict[str, Any]:
    value = report
    for key in path:
        value = _as_dict(value).get(key)
    return _as_dict(value)


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _format_value(
    value: Any,
    *,
    kind: str = "number",
    status: Any = None,
    currency: str | None = None,
) -> str:
    status_text = status.strip().casefold() if isinstance(status, str) else ""
    if status_text in {"not_meaningful", "n/m"} or status_text.startswith("not meaningful"):
        return "N/M"
    if isinstance(value, str):
        text = value.strip()
        if text.casefold() in {"n/a", "n/m"}:
            return text.upper()
        if text:
            return text
    number = _numeric(value)
    if number is None:
        return "N/A"
    if kind == "percent":
        return f"{number:.1f}%"
    if kind == "fraction_percent":
        return f"{number:.1%}"
    if kind == "currency":
        return format_market_price(number, currency)
    if kind == "money":
        return f"${number:,.0f}"
    if kind == "integer":
        return f"{number:,.0f}"
    if kind == "multiple":
        return f"{number:.2f}x"
    if kind == "ratio":
        return f"{number:.2f}"
    return f"{number:,.2f}"


def _add_metric(
    evidence: dict[str, Any],
    label: str,
    value: Any,
    *,
    group: str = "",
    kind: str = "number",
    status: Any = None,
    currency: str | None = None,
) -> None:
    evidence["metrics"].append({
        "label": label,
        "value": _format_value(value, kind=kind, status=status, currency=currency),
        "group": group,
    })


def _add_bullets(evidence: dict[str, Any], title: str, values: Any) -> None:
    if isinstance(values, str):
        items = [values.strip()] if values.strip() else []
    else:
        items = [
            item.strip() for item in _as_list(values)
            if isinstance(item, str) and item.strip()
        ]
    if items:
        evidence["bullets"].append({"title": title, "items": items})


def _add_paragraph(evidence: dict[str, Any], title: str, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        evidence["paragraphs"].append({"title": title, "text": value.strip()})


def _add_table(
    evidence: dict[str, Any],
    title: str,
    columns: list[str],
    rows: list[dict[str, str]],
) -> None:
    if rows:
        evidence["tables"].append({
            "title": title,
            "columns": columns,
            "rows": rows,
        })


def _period_value(values: Any, index: int) -> Any:
    items = _as_list(values)
    return items[index] if index < len(items) else None


def _revenue_stage(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "N/A"
    return {
        "pre_revenue": "Pre-revenue",
        "not_meaningful": "N/M",
        "unavailable": "N/A",
        "operating": "Operating",
    }.get(value.strip().casefold(), value.strip())


def _peer_table(peer_data: dict[str, Any], labels: tuple[str, ...]) -> tuple[list[str], list[dict[str, str]]]:
    frame = peer_data.get("df")
    tickers = peer_data.get("tickers")
    if frame is None or not isinstance(tickers, list):
        return [], []
    try:
        available_rows = set(frame.index)
        available_columns = set(frame.columns)
        columns = [ticker for ticker in tickers if ticker in available_columns]
        rows = []
        for label in labels:
            if label not in available_rows:
                continue
            row = {"Metric": label}
            kind = (
                "percent" if label in {"Revenue Growth", "Operating Margin", "ROE"}
                else "multiple" if label in {"P/E", "Forward P/E", "EV/EBITDA"}
                else "ratio"
            )
            for ticker in columns:
                row[str(ticker)] = _format_value(frame.loc[label, ticker], kind=kind)
            rows.append(row)
        return ["Metric", *[str(ticker) for ticker in columns]], rows
    except (AttributeError, KeyError, TypeError, ValueError):
        return [], []


def _evidence_template() -> dict[str, Any]:
    return {
        "metrics": [],
        "tables": [],
        "bullets": [],
        "paragraphs": [],
        "available": False,
    }


def _valuation_evidence(report: Any, evidence: dict[str, Any]) -> None:
    valuation = _section(report, "ratios", "valuation")
    metric_specs = (
        ("Trailing P/E", "trailing_pe", "multiple", "trailing_pe_status"),
        ("Forward P/E", "forward_pe", "multiple", "forward_pe_status"),
        ("PEG", "peg", "multiple", "peg_status"),
        ("EV / EBITDA", "ev_ebitda", "multiple", "ev_ebitda_status"),
        ("Price / Book", "pb", "multiple", "pb_status"),
        ("EV / Revenue", "ev_revenue", "multiple", "ev_revenue_status"),
        ("Price / Sales", "price_to_sales", "multiple", "price_to_sales_status"),
    )
    for label, key, kind, status_key in metric_specs:
        _add_metric(
            evidence, label, valuation.get(key), group="Valuation multiples",
            kind=kind, status=valuation.get(status_key),
        )

    peer_data = _as_dict(report.get("peers")) if isinstance(report, dict) else {}
    columns, rows = _peer_table(peer_data, ("P/E", "Forward P/E", "EV/EBITDA"))
    _add_table(evidence, "Peer valuation comparison", columns, rows)


def _financial_quality_evidence(report: Any, evidence: dict[str, Any]) -> None:
    ratios = _section(report, "ratios")
    profitability = _as_dict(ratios.get("profitability"))
    strength = _as_dict(ratios.get("strength"))
    financials = _section(report, "financials")
    cashflow = _as_dict(financials.get("cashflow"))
    income = _as_dict(financials.get("income"))
    balance = _as_dict(financials.get("balance"))
    sector = str(_section(report, "company").get("sector") or "").casefold()
    financial_sector = any(
        token in sector for token in ("bank", "financial", "insurance", "broker", "asset management")
    )

    for label, key, status_key in (
        ("Net Margin", "net_margin", "net_margin_status"),
        ("Operating Margin", "op_margin", "op_margin_status"),
    ):
        _add_metric(
            evidence, label, profitability.get(key), group="Profitability",
            kind="percent", status=profitability.get(status_key),
        )
    for label, key in (("ROE", "roe"), ("ROA", "roa")):
        _add_metric(evidence, label, profitability.get(key), group="Profitability", kind="percent")

    _add_metric(
        evidence, "Operating Cash Flow", cashflow.get("operating_cf"),
        group="Cash Flow / Financial Strength", kind="money",
    )
    _add_metric(
        evidence, "Free Cash Flow", cashflow.get("free_cash_flow"),
        group="Cash Flow / Financial Strength", kind="money",
    )
    if not financial_sector:
        for label, key in (
            ("Debt / Equity", "de_ratio"),
            ("Current Ratio", "current_ratio"),
            ("Cash / Debt", "cash_to_debt"),
        ):
            source = strength if key in strength else balance
            _add_metric(
                evidence, label, source.get(key), group="Cash Flow / Financial Strength",
                kind="ratio",
                status=balance.get("de_note") if key == "de_ratio" else None,
            )


def _growth_evidence(report: Any, evidence: dict[str, Any]) -> None:
    financials = _section(report, "financials")
    income = _as_dict(financials.get("income"))
    years = _as_list(income.get("years"))
    revenues = _as_list(income.get("revenue"))
    growth = _as_list(income.get("revenue_growth"))
    growth_status = _as_list(income.get("revenue_growth_status"))
    rows = []
    for index, year in enumerate(years):
        revenue_status = _period_value(income.get("revenue_status"), index)
        rows.append({
            "Year": str(year) if year is not None else "N/A",
            "Revenue": _format_value(_period_value(revenues, index), kind="money", status=revenue_status),
            "Revenue Growth": _format_value(
                _period_value(growth, index),
                kind="percent",
                status=_period_value(growth_status, index),
            ),
        })
    _add_table(evidence, "Historical revenue", ["Year", "Revenue", "Revenue Growth"], rows)

    stage = _revenue_stage(income.get("revenue_stage"))
    _add_metric(evidence, "Revenue Stage", stage, group="Growth trend")
    _add_metric(evidence, "Revenue Growth Trend", income.get("acceleration"), group="Growth trend")
    op_margin = _as_list(income.get("op_margin"))
    if op_margin:
        _add_metric(
            evidence, "Latest Operating Margin", op_margin[0], group="Growth trend",
            kind="percent", status=_period_value(income.get("op_margin_status"), 0),
        )

    expectations = _section(report, "expectations", "revenue_estimates")
    forward_rows = []
    for period_key, label in (("current_year", "Current Year"), ("next_year", "Next Year")):
        estimate = _as_dict(expectations.get(period_key))
        forward_rows.append({
            "Period": label,
            "Revenue Estimate": _format_value(estimate.get("revenue"), kind="money"),
            "Expected Growth": _format_value(
                estimate.get("growth"),
                kind="fraction_percent",
                status=estimate.get("growth_status"),
            ),
        })
    if expectations:
        _add_table(
            evidence, "Forward revenue expectations",
            ["Period", "Revenue Estimate", "Expected Growth"], forward_rows,
        )


def _risk_evidence(report: Any, evidence: dict[str, Any]) -> None:
    company_analysis = _section(report, "company_analysis", "analysis")
    market_review = _section(report, "market_review", "review")
    bull_bear = _section(report, "bull_bear", "analysis")
    _add_bullets(evidence, "Key Factors to Watch", company_analysis.get("key_factors_to_watch"))
    _add_bullets(evidence, "Industry Risks", market_review.get("industry_risks"))
    _add_bullets(evidence, "Bear Case", bull_bear.get("bear_case"))

    financials = _section(report, "financials")
    ratios = _section(report, "ratios")
    cashflow = _as_dict(financials.get("cashflow"))
    strength = _as_dict(ratios.get("strength"))
    for label, value, kind in (
        ("Debt / Equity", strength.get("de_ratio"), "ratio"),
        ("Current Ratio", strength.get("current_ratio"), "ratio"),
        ("Operating Cash Flow", cashflow.get("operating_cf"), "money"),
        ("Free Cash Flow", cashflow.get("free_cash_flow"), "money"),
    ):
        if _numeric(value) is not None:
            _add_metric(evidence, label, value, group="Financial risk metrics", kind=kind)


def _volatility_evidence(report: Any, evidence: dict[str, Any]) -> None:
    performance = _section(report, "price_performance")
    components = _section(report, "assessment", "indicators", "volatility", "components")
    component_sources = {
        "annualized_volatility": "annualized_volatility",
        "beta": "beta",
        "max_drawdown": "max_drawdown",
    }
    for label, key, kind in (
        ("Annualized Volatility", "annualized_volatility", "fraction_percent"),
        ("Beta", "beta", "number"),
        ("Max Drawdown", "max_drawdown", "fraction_percent"),
    ):
        component = _as_dict(components.get(component_sources[key]))
        value = component.get("value") if "value" in component else performance.get(key)
        _add_metric(evidence, label, value, group="Volatility summary", kind=kind)

    returns = _as_dict(performance.get("returns"))
    for key, label in (("1 Month", "1 Month Return"), ("6 Months", "6 Month Return"), ("1 Year", "1 Year Return")):
        _add_metric(
            evidence, label, returns.get(key), group="Price performance",
            kind="fraction_percent",
        )
    price_range = _as_dict(performance.get("range"))
    currency = _section(report, "company").get("currency")
    _add_metric(
        evidence, "Current Price", price_range.get("current_price"),
        group="52-week range", kind="currency", currency=currency,
    )
    _add_metric(
        evidence, "52-week High", price_range.get("high"),
        group="52-week range", kind="currency", currency=currency,
    )
    _add_metric(
        evidence, "52-week Low", price_range.get("low"),
        group="52-week range", kind="currency", currency=currency,
    )


def _market_evidence(report: Any, evidence: dict[str, Any]) -> None:
    review = _section(report, "market_review", "review")
    for title, key in (
        ("Market Outlook", "market_outlook"),
        ("Regulatory Environment", "regulatory_environment"),
        ("Macro Exposure", "macro_exposure"),
    ):
        _add_paragraph(evidence, title, review.get(key))
    for title, key in (
        ("Growth Drivers", "growth_drivers"),
        ("Industry Risks", "industry_risks"),
        ("Company Implications", "company_implications"),
    ):
        _add_bullets(evidence, title, review.get(key))


def _competitive_evidence(report: Any, evidence: dict[str, Any]) -> None:
    company_analysis = _section(report, "company_analysis", "analysis")
    market_review = _section(report, "market_review", "review")
    _add_paragraph(evidence, "Peer Positioning", company_analysis.get("peer_positioning"))
    _add_bullets(evidence, "Competitive Dynamics", market_review.get("competitive_dynamics"))
    peer_data = _as_dict(report.get("peers")) if isinstance(report, dict) else {}
    columns, rows = _peer_table(
        peer_data,
        ("Revenue Growth", "Operating Margin", "ROE", "Debt/Equity"),
    )
    _add_table(evidence, "Peer comparison", columns, rows)


def _expectations_evidence(report: Any, evidence: dict[str, Any]) -> None:
    expectations = _section(report, "expectations")
    targets = _as_dict(expectations.get("price_targets"))
    currency = targets.get("currency") or _section(report, "company").get("currency")
    for label, key, kind in (
        ("Current Price", "current_price", "currency"),
        ("Average Target", "average_target", "currency"),
        ("Median Target", "median_target", "currency"),
        ("High Target", "high_target", "currency"),
        ("Low Target", "low_target", "currency"),
        ("Implied Upside", "implied_upside", "fraction_percent"),
        ("Analyst Count", "analysts", "integer"),
    ):
        _add_metric(
            evidence, label, targets.get(key), group="Price targets", kind=kind,
            currency=currency if kind == "currency" else None,
        )

    recommendations = _as_dict(expectations.get("recommendations"))
    _add_metric(evidence, "Consensus", recommendations.get("consensus"), group="Analyst view")
    counts = _as_dict(recommendations.get("counts"))
    for label in ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"):
        _add_metric(evidence, label, counts.get(label), group="Recommendation mix", kind="integer")

    revenue_estimates = _as_dict(expectations.get("revenue_estimates"))
    rows = []
    for key, label in (("current_year", "Current Year"), ("next_year", "Next Year")):
        estimate = _as_dict(revenue_estimates.get(key))
        rows.append({
            "Period": label,
            "Revenue Estimate": _format_value(estimate.get("revenue"), kind="money"),
            "Expected Growth": _format_value(
                estimate.get("growth"),
                kind="fraction_percent",
                status=estimate.get("growth_status"),
            ),
        })
    if revenue_estimates:
        _add_table(
            evidence, "Revenue estimates",
            ["Period", "Revenue Estimate", "Expected Growth"], rows,
        )


_EVIDENCE_BUILDERS = {
    "valuation": _valuation_evidence,
    "financial_quality": _financial_quality_evidence,
    "growth": _growth_evidence,
    "risk": _risk_evidence,
    "volatility": _volatility_evidence,
    "market_environment": _market_evidence,
    "competitive_position": _competitive_evidence,
    "expectations": _expectations_evidence,
}


def get_indicator_evidence_display(
    report: Any,
    indicator_key: str,
    indicator_name: str,
) -> dict[str, Any]:
    """Return only formatted evidence selected for one assessment indicator."""
    evidence = _evidence_template()
    evidence["name"] = indicator_name
    builder = _EVIDENCE_BUILDERS.get(indicator_key)
    if builder is not None:
        builder(report, evidence)
    evidence["available"] = any(
        evidence[key] for key in ("metrics", "tables", "bullets", "paragraphs")
    )
    return evidence


def get_assessment_display(report: Any) -> list[dict[str, str]]:
    """Return the eight dashboard indicators without assessment internals."""
    return [
        get_indicator_display(report, key, name)
        for key, name in ASSESSMENT_INDICATORS
    ]


def get_assessment_evidence_display(report: Any) -> list[dict[str, Any]]:
    """Return ordered user-facing evidence blocks for all eight assessment indicators."""
    return [
        get_indicator_evidence_display(report, key, name)
        for key, name in ASSESSMENT_INDICATORS
    ]
