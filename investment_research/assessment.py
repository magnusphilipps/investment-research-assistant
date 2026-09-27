from __future__ import annotations

import math
from typing import Any

from . import gemini_provider
from .assessment_scoring import (
    array_first,
    build_driver,
    compare_to_peer,
    deep_find_value,
    metric_median,
    peer_coverage_label,
    peer_metric_values,
    percent_from_value,
    safe_numeric,
    unavailable_indicator,
    valid_metric_values,
    weighted_average,
)


def _normalise_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _close_value(obj: Any, names: list[str]) -> Any:
    if obj is None:
        return None
    found = deep_find_value(obj, names)
    if found is not None:
        return found
    return None


def _metric_component(name: str, value: Any, score: float | None, **extra: Any) -> dict[str, Any]:
    component: dict[str, Any] = {"value": value, "score": score}
    for key, item in extra.items():
        if item is not None:
            component[key] = item
    return component


def _normalise_label(label: str | None) -> str:
    if not label:
        return "N/A"
    return label.strip()


def _evaluate_peer_relative(metric_name: str, company_value: Any, peer_values: list[float], *, alias_candidates: list[str]) -> tuple[float | None, dict[str, Any], str | None]:
    company = safe_numeric(company_value)
    if company is None or company <= 0:
        return None, {"metric": metric_name, "company_value": company, "peer_values": peer_values, "excluded": ["negative or zero value"]}, None

    valid_values = [float(v) for v in peer_values if safe_numeric(v) is not None and safe_numeric(v) > 0]
    if len(valid_values) == 0:
        return None, {"metric": metric_name, "company_value": company, "peer_values": [], "excluded": ["no valid peer values"]}, None

    if len(valid_values) == 1:
        return None, {"metric": metric_name, "company_value": company, "peer_counter": valid_values, "excluded": ["insufficient peer coverage"]}, None

    median_value = metric_median(valid_values)
    if median_value is None or median_value <= 0:
        return None, {"metric": metric_name, "company_value": company, "peer_values": valid_values, "excluded": ["peer median unavailable"]}, None

    score = compare_to_peer(company, median_value)
    if score is None:
        return None, {"metric": metric_name, "company_value": company, "peer_values": valid_values, "peer_median": median_value}, None

    component = {
        "metric": metric_name,
        "company_value": company,
        "peer_values": valid_values,
        "peer_median": median_value,
        "score": score,
    }
    if len(valid_values) >= 3:
        coverage = "strong"
    else:
        coverage = "acceptable"
    return score, component, coverage


def _peer_metric_candidates(metric: str, *extra_aliases: str) -> list[str]:
    aliases = [metric, *extra_aliases]
    return list(dict.fromkeys(aliases))


def _peer_data_for_metric(peer_data: Any, metric: str, *extra_aliases: str) -> list[float]:
    aliases = _peer_metric_candidates(metric, *extra_aliases)
    values = peer_metric_values(peer_data, aliases)
    return [float(v) for v in values if safe_numeric(v) is not None and safe_numeric(v) > 0]


def _standard_indicator(label: str, score: float | None, drivers: list[str], components: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "score": score,
        "drivers": drivers,
        "components": components,
        "evidence": evidence,
    }


def _build_indicator_from_scores(label: str, score: float | None, weights: list[float], raw_components: list[tuple[str, float | None, dict[str, Any]]], *, evidence: dict[str, Any]) -> dict[str, Any]:
    components: dict[str, Any] = {}
    valid = []
    for name, value, data in raw_components:
        if value is None:
            continue
        components[name] = data
        valid.append(value)
    drivers: list[str] = []
    if valid:
        positive = sorted(raw_components, key=lambda item: abs(item[1]) if item[1] is not None else 0.0, reverse=True)
        for name, value, data in positive[:3]:
            if value is None:
                continue
            if value >= 0:
                drivers.append(f"{name} remains supportive.")
            else:
                drivers.append(f"{name} is a drag on the overall assessment.")
        if not drivers:
            drivers = ["The available evidence is mixed."]
    else:
        drivers = ["Insufficient data to calculate this indicator."]
    return _standard_indicator(label, score, drivers[:3], components, evidence)


def _gather_company_context(context: dict[str, Any]) -> dict[str, Any]:
    company = _normalise_dict(context.get("company"))
    financials = _normalise_dict(context.get("financials"))
    ratios = _normalise_dict(context.get("ratios"))
    valuation = _normalise_dict(context.get("valuation"))
    performance = _normalise_dict(context.get("performance"))
    expectations = _normalise_dict(context.get("analyst_expectations"))
    peer_data = context.get("peer_comparison")
    if not peer_data and isinstance(context.get("peers"), dict):
        peer_data = context.get("peers")
    if not peer_data and isinstance(context.get("peer_comparison_data"), dict):
        peer_data = context.get("peer_comparison_data")
    return {
        "company": company,
        "financials": financials,
        "ratios": ratios,
        "valuation": valuation,
        "performance": performance,
        "expectations": expectations,
        "peer_comparison": peer_data,
    }


def assess_valuation(context: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic valuation indicator without new data collection."""
    context = _gather_company_context(context or {})
    company = context["company"]
    financials = context["financials"]
    ratios = context["ratios"]
    valuation = context["valuation"]
    peer_data = context["peer_comparison"]

    valuation_map = _normalise_dict(valuation)
    if not valuation_map and isinstance(ratios, dict):
        valuation_map = _normalise_dict(ratios.get("valuation"))

    candidate_metrics = []
    earnings = []
    sales = []

    def record(metric_name: str, value: Any, key_aliases: list[str], bucket: str) -> None:
        numeric = safe_numeric(value)
        if numeric is None or ("pe" in metric_name.lower() or "ebitda" in metric_name.lower()) and numeric <= 0:
            return
        if numeric > 0:
            candidate_metrics.append((metric_name, value, key_aliases, bucket))
            if bucket == "earnings":
                earnings.append((metric_name, value))
            elif bucket == "sales":
                sales.append((metric_name, value))

    for item in [
        ("P/E", _close_value(valuation_map, ["trailing_pe", "trailingPE", "P/E", "pe"]) , ["trailing_pe", "trailingPE", "P/E", "pe"], "earnings"),
        ("Forward P/E", _close_value(valuation_map, ["forward_pe", "forwardPE", "Forward P/E", "forward_pe"]) , ["forward_pe", "forwardPE", "Forward P/E", "forward_pe"], "earnings"),
        ("EV/EBITDA", _close_value(valuation_map, ["ev_ebitda", "enterpriseToEbitda", "EV/EBITDA"]), ["ev_ebitda", "enterpriseToEbitda", "EV/EBITDA"], "earnings"),
        ("PEG", _close_value(valuation_map, ["peg", "pegRatio", "PEG"]), ["peg", "pegRatio", "PEG"], "earnings"),
        ("P/B", _close_value(valuation_map, ["pb", "priceToBook", "P/B"]), ["pb", "priceToBook", "P/B"], "earnings"),
        ("EV/Revenue", _close_value(valuation_map, ["ev_revenue", "enterpriseToRevenue", "EV/Revenue"]), ["ev_revenue", "enterpriseToRevenue", "EV/Revenue"], "sales"),
        ("Price/Sales", _close_value(valuation_map, ["price_to_sales", "priceToSales", "Price/Sales", "ps"]), ["price_to_sales", "priceToSales", "Price/Sales", "ps"], "sales"),
        ("Forward EV/Revenue", _close_value(valuation_map, ["forward_ev_revenue", "forwardEnterpriseValueToRevenue", "Forward EV/Revenue"]), ["forward_ev_revenue", "forwardEnterpriseValueToRevenue", "Forward EV/Revenue"], "sales"),
    ]:
        record(*item)

    # The repository already exposes financial statements and ratios; use them if the market
    # valuation dict is sparse or partially missing.
    if not earnings and financials:
        income = _normalise_dict(financials.get("income"))
        net_income = array_first(income.get("net_income"))
        if safe_numeric(net_income) is not None and safe_numeric(net_income) > 0:
            pe_from_fin = _close_value(ratios, ["valuation", "trailing_pe", "trailingPE", "P/E", "pe"]) or _close_value(financials, ["trailing_pe", "trailingPE"])
            if pe_from_fin is not None:
                candidate_metrics.append(("P/E", pe_from_fin, ["trailing_pe", "trailingPE", "P/E", "pe"], "earnings"))

    mode = "unavailable"
    if earnings and sales:
        mode = "mixed"
    elif earnings:
        mode = "earnings"
    elif sales:
        mode = "sales"

    if mode == "unavailable":
        return unavailable_indicator("Insufficient comparable valuation data.")

    valid_components: dict[str, Any] = {}
    excluded_metrics: list[str] = []
    scores: list[float] = []
    component_weights: list[float] = []

    for metric_name, value, aliases, bucket in candidate_metrics:
        if safe_numeric(value) is None and value is not None:
            excluded_metrics.append(f"{metric_name}: invalid value")
            continue
        if safe_numeric(value) is not None and safe_numeric(value) <= 0:
            excluded_metrics.append(f"{metric_name}: non-positive value")
            continue

        peer_values = _peer_data_for_metric(peer_data, metric_name, *aliases)
        score, component, coverage = _evaluate_peer_relative(metric_name, value, peer_values, alias_candidates=aliases)
        if score is None:
            excluded_metrics.append(f"{metric_name}: insufficient peer coverage")
            continue

        valid_components[metric_name] = component
        scores.append(float(score))
        component_weights.append(1.0)

    if len(valid_components) < 2:
        return unavailable_indicator("Insufficient comparable valuation data.")

    aggregate = sum(scores) / len(scores) if scores else 0.0
    if aggregate >= 0.75:
        label = "Cheap"
    elif aggregate <= -0.75:
        label = "Expensive"
    else:
        label = "Fair"

    drivers: list[str] = []
    sorted_components = sorted(valid_components.items(), key=lambda item: abs(item[1].get("score", 0.0)), reverse=True)
    for metric_name, component in sorted_components[:3]:
        score = component.get("score", 0.0)
        peer_median = component.get("peer_median")
        company_value = component.get("company_value")
        if score >= 1:
            direction = "below"
            if metric_name.startswith("Forward"):
                drivers.append(f"{metric_name} trades below the peer median.")
            else:
                drivers.append(f"{metric_name} is materially cheaper than peer median {peer_median:.2f}.")
        elif score <= -1:
            direction = "above"
            if metric_name.startswith("Forward"):
                drivers.append(f"{metric_name} trades above the peer median.")
            else:
                drivers.append(f"{metric_name} is materially above peer median {peer_median:.2f}.")
        else:
            drivers.append(f"{metric_name} is broadly in line with peers.")

    evidence = {
        "valid_component_count": len(valid_components),
        "total_possible_components": len(candidate_metrics),
        "valuation_mode": mode,
        "peer_coverage": peer_coverage_label(len(valid_components)),
        "excluded_metrics": excluded_metrics,
        "missing_inputs": [],
    }
    return _standard_indicator(label, aggregate, drivers[:3], valid_components, evidence)


def assess_financial_quality(context: dict[str, Any] | None) -> dict[str, Any]:
    """Assess the resilience and operating quality of the business."""
    context = _gather_company_context(context or {})
    company = context["company"]
    financials = context["financials"]
    ratios = context["ratios"]
    peer_data = context["peer_comparison"]

    sector = str(company.get("sector") or "").lower()
    is_financial = any(token in sector for token in ["bank", "financial", "insurance", "broker", "asset management"])

    components: dict[str, Any] = {}
    excluded: list[str] = []
    score_rows: list[tuple[str, float, dict[str, Any]]] = []

    # FCF margin
    revenue = None
    if isinstance(financials, dict):
        income = _normalise_dict(financials.get("income"))
        revenue = array_first(income.get("revenue"))
    if revenue is not None:
        fcf = None
        if isinstance(financials, dict):
            cashflow = _normalise_dict(financials.get("cashflow"))
            fcf = array_first(cashflow.get("free_cash_flow"))
        if fcf is not None:
            margin = percent_from_value(fcf, revenue)
            if margin is not None:
                if margin > 15:
                    score = 2.0
                elif margin >= 5:
                    score = 1.0
                elif margin >= 0:
                    score = 0.0
                else:
                    score = -2.0
                components["fcf_margin"] = {"value": margin, "score": score, "type": "margin"}
                score_rows.append(("FCF margin", score, components["fcf_margin"]))
            else:
                excluded.append("fcf_margin: no usable revenue or FCF")
    else:
        excluded.append("fcf_margin: revenue missing")

    # Operating margin relative to peers
    op_margin_company = safe_numeric(_close_value(ratios, ["profitability", "op_margin", "Operating Margin"]))
    if op_margin_company is not None:
        peer_values = _peer_data_for_metric(peer_data, "Operating Margin", "op_margin")
        if peer_values:
            peer_median = metric_median(peer_values)
            if peer_median is not None:
                delta = op_margin_company - peer_median
                if delta >= 10:
                    score = 2.0
                elif delta >= 3:
                    score = 1.0
                elif abs(delta) <= 3:
                    score = 0.0
                elif delta <= -3:
                    score = -1.0
                else:
                    score = -2.0
                components["operating_margin"] = {"value": op_margin_company, "peer_median": peer_median, "score": score, "type": "peer_relative"}
                score_rows.append(("Operating margin", score, components["operating_margin"]))
            else:
                excluded.append("operating_margin: peer median unavailable")
        else:
            excluded.append("operating_margin: insufficient peer values")

    # Operating cash flow
    ocf = None
    if isinstance(financials, dict):
        cashflow = _normalise_dict(financials.get("cashflow"))
        ocf = safe_numeric(array_first(cashflow.get("operating_cf")))
    if ocf is not None:
        score = 1.0 if ocf > 0 else -2.0 if ocf < 0 else 0.0
        components["operating_cash_flow"] = {"value": ocf, "score": score}
        score_rows.append(("Operating cash flow", score, components["operating_cash_flow"]))

    # Debt/equity and current ratio only for non-financial companies
    if not is_financial:
        de_ratio = safe_numeric(_close_value(ratios, ["strength", "de_ratio", "Debt/Equity", "de_ratio"]))
        if de_ratio is not None:
            if de_ratio < 0.5:
                score = 1.0
            elif de_ratio <= 1.5:
                score = 0.0
            elif de_ratio <= 2.5:
                score = -1.0
            else:
                score = -2.0
            components["debt_to_equity"] = {"value": de_ratio, "score": score}
            score_rows.append(("Debt/Equity", score, components["debt_to_equity"]))
        else:
            excluded.append("debt_to_equity: unavailable")

        current_ratio = safe_numeric(_close_value(ratios, ["strength", "current_ratio", "Current Ratio", "currentRatio"]))
        if current_ratio is not None:
            if current_ratio > 1.5:
                score = 1.0
            elif current_ratio >= 1.0:
                score = 0.0
            elif current_ratio >= 0.75:
                score = -1.0
            else:
                score = -2.0
            components["current_ratio"] = {"value": current_ratio, "score": score}
            score_rows.append(("Current ratio", score, components["current_ratio"]))
        else:
            excluded.append("current_ratio: unavailable")
    else:
        excluded.append("sector_adjustment: bank/financial company path used; industrial balance-sheet ratios omitted")

    if len(score_rows) < 2:
        return unavailable_indicator("Insufficient data for financial quality.")

    aggregate = sum(item[1] for item in score_rows) / len(score_rows)
    if aggregate >= 0.75:
        label = "Strong"
    elif aggregate <= -0.75:
        label = "Weak"
    else:
        label = "Moderate"

    drivers: list[str] = []
    for name, score, data in sorted(score_rows, key=lambda x: abs(x[1]), reverse=True)[:3]:
        if score >= 1:
            drivers.append(f"{name} remains supportive.")
        elif score <= -1:
            drivers.append(f"{name} is a material weakness.")
        else:
            drivers.append(f"{name} is near neutral.")

    evidence = {
        "valid_component_count": len(score_rows),
        "total_possible_components": max(2, len(score_rows) + len(excluded)),
        "sector_adjustments": ["industrial ratios omitted for financial institution"] if is_financial else [],
        "excluded_components": excluded,
    }
    return _standard_indicator(label, aggregate, drivers[:3], components, evidence)


def assess_growth(context: dict[str, Any] | None) -> dict[str, Any]:
    """Assess the underlying business growth profile."""
    context = _gather_company_context(context or {})
    financials = context["financials"]
    expectations = context["expectations"]

    income = _normalise_dict(financials.get("income")) if isinstance(financials, dict) else {}
    revenue_growth = income.get("revenue_growth") if isinstance(revenue_growth := income.get("revenue_growth"), list) else []
    hist_value = safe_numeric(array_first(revenue_growth))
    forward_value = None
    revenue_estimates = _normalise_dict(expectations.get("revenue_estimates")) if isinstance(expectations, dict) else {}
    next_year = _normalise_dict(revenue_estimates.get("next_year")) if isinstance(revenue_estimates, dict) else {}
    if next_year:
        forward_value = safe_numeric(next_year.get("growth"))
    if forward_value is None:
        forward_value = safe_numeric(_close_value(expectations, ["forward_revenue_growth", "revenue_growth", "growth"]))

    dimension_scores = []
    components: dict[str, Any] = {}

    def score_growth(value: float | None) -> float | None:
        if value is None:
            return None
        if value > 20:
            return 2.0
        if value >= 10:
            return 1.0
        if value >= 3:
            return 0.0
        if value >= 0:
            return -1.0
        return -2.0

    if hist_value is not None:
        score = score_growth(hist_value)
        components["historical_revenue_growth"] = {"value": hist_value, "score": score}
        dimension_scores.append((0.35, score))
    if forward_value is not None:
        score = score_growth(forward_value)
        components["forward_revenue_growth"] = {"value": forward_value, "score": score}
        dimension_scores.append((0.35, score))

    trajectory = None
    if isinstance(revenue_growth, list) and len(revenue_growth) >= 2:
        recent = [safe_numeric(v) for v in revenue_growth[:3] if safe_numeric(v) is not None]
        if len(recent) >= 2:
            latest = recent[0]
            prior = recent[-1]
            if latest > prior:
                trajectory = 1.0
            elif latest < prior:
                trajectory = -1.0
            else:
                trajectory = 0.0
    if trajectory is not None:
        components["growth_trajectory"] = {"value": trajectory, "score": trajectory}
        dimension_scores.append((0.15, trajectory))

    margin_trajectory = None
    op_margins = []
    if isinstance(financials, dict):
        op_margins = [safe_numeric(v) for v in _normalise_dict(financials.get("income")).get("op_margin", []) if safe_numeric(v) is not None]
    if len(op_margins) >= 2:
        latest_margin = op_margins[0]
        prior_margin = op_margins[-1]
        if latest_margin > prior_margin:
            margin_trajectory = 1.0
        elif latest_margin < prior_margin:
            margin_trajectory = -1.0
        else:
            margin_trajectory = 0.0
    if margin_trajectory is not None:
        components["margin_trajectory"] = {"value": margin_trajectory, "score": margin_trajectory}
        dimension_scores.append((0.15, margin_trajectory))

    if not dimension_scores:
        return unavailable_indicator("Insufficient data to calculate growth.")

    total_weight = sum(weight for weight, _ in dimension_scores)
    aggregate = sum(score * weight for weight, score in dimension_scores if score is not None) / total_weight
    if aggregate >= 0.75:
        label = "Strong"
    elif aggregate <= -0.50:
        label = "Weak"
    else:
        label = "Moderate"

    drivers: list[str] = []
    for name, score in sorted([(name, data.get("score")) for name, data in components.items() if data.get("score") is not None], key=lambda item: abs(item[1]), reverse=True)[:3]:
        if score is None:
            continue
        if score >= 1:
            drivers.append(f"{name.replace('_', ' ').title()} remains supportive.")
        elif score <= -1:
            drivers.append(f"{name.replace('_', ' ').title()} is a drag on growth.")
        else:
            drivers.append(f"{name.replace('_', ' ').title()} is near neutral.")
    if not drivers:
        drivers = ["Growth is mixed across available measures."]

    evidence = {
        "valid_component_count": len(components),
        "total_possible_components": 4,
        "weights": {"historical_revenue_growth": 0.35, "forward_revenue_growth": 0.35, "growth_trajectory": 0.15, "margin_trajectory": 0.15},
    }
    return _standard_indicator(label, aggregate, drivers[:3], components, evidence)


def assess_volatility(context: dict[str, Any] | None) -> dict[str, Any]:
    """Fully deterministic volatility assessment using historical price data."""
    context = _gather_company_context(context or {})
    performance = context["performance"]
    if not isinstance(performance, dict):
        return unavailable_indicator("Insufficient price history for volatility.")

    components: dict[str, Any] = {}
    scores: list[float] = []
    evidence: dict[str, Any] = {"valid_component_count": 0, "excluded_components": []}

    # Annualized volatility
    annualized = safe_numeric(performance.get("annualized_volatility"))
    if annualized is None:
        daily_returns = performance.get("daily_returns")
        if isinstance(daily_returns, list):
            values = [safe_numeric(v) for v in daily_returns if safe_numeric(v) is not None]
            if values:
                annualized = math.sqrt(252) * (sum((v - sum(values) / len(values)) ** 2 for v in values) / (len(values) - 1) if len(values) > 1 else 0) ** 0.5
        else:
            annualized = None
    if annualized is not None:
        if annualized < 0.20:
            score = 0.0
        elif annualized <= 0.35:
            score = 1.0
        else:
            score = 2.0
        components["annualized_volatility"] = {"value": annualized, "score": score}
        scores.append(score)
    else:
        evidence["excluded_components"].append("annualized_volatility")

    beta = safe_numeric(performance.get("beta"))
    if beta is not None:
        if beta < 0.8:
            score = 0.0
        elif beta <= 1.2:
            score = 1.0
        else:
            score = 2.0
        components["beta"] = {"value": beta, "score": score}
        scores.append(score)
    else:
        evidence["excluded_components"].append("beta")

    max_drawdown = safe_numeric(performance.get("max_drawdown"))
    if max_drawdown is not None:
        magnitude = abs(max_drawdown)
        if magnitude < 0.15:
            score = 0.0
        elif magnitude <= 0.30:
            score = 1.0
        else:
            score = 2.0
        components["max_drawdown"] = {"value": magnitude, "score": score}
        scores.append(score)
    else:
        evidence["excluded_components"].append("max_drawdown")

    if not scores:
        return unavailable_indicator("Insufficient price history for volatility.")

    aggregate = sum(scores) / len(scores)
    if aggregate < 0.67:
        label = "Low"
    elif aggregate <= 1.33:
        label = "Medium"
    else:
        label = "High"

    drivers = []
    sorted_components = sorted(components.items(), key=lambda item: abs(item[1].get("score", 0.0)), reverse=True)
    for name, data in sorted_components[:3]:
        score = data.get("score", 0.0)
        if score < 1:
            drivers.append(f"{name.replace('_', ' ').title()} remains reassuringly low.")
        elif score > 1:
            drivers.append(f"{name.replace('_', ' ').title()} is elevated.")
        else:
            drivers.append(f"{name.replace('_', ' ').title()} is in a moderate range.")
    if not drivers:
        drivers = ["Volatility is broadly moderate."]

    evidence["valid_component_count"] = len(scores)
    return _standard_indicator(label, aggregate, drivers[:3], components, evidence)


def assess_expectations(context: dict[str, Any] | None) -> dict[str, Any]:
    """Assess the market / analyst expectation profile."""
    context = _gather_company_context(context or {})
    expectations = context["expectations"]
    if not isinstance(expectations, dict):
        return unavailable_indicator("Insufficient analyst expectation data.")

    components: dict[str, Any] = {}
    weighted = []
    excluded: list[str] = []

    # forward revenue growth
    forward_growth = None
    revenue_estimates = expectations.get("revenue_estimates") if isinstance(expectations, dict) else {}
    if isinstance(revenue_estimates, dict):
        next_year = revenue_estimates.get("next_year")
        if isinstance(next_year, dict):
            forward_growth = safe_numeric(next_year.get("growth"))
    if forward_growth is None:
        forward_growth = safe_numeric(_close_value(expectations, ["forward_revenue_growth", "revenue_growth"]))
    if forward_growth is not None:
        if forward_growth > 15:
            score = 2.0
        elif forward_growth >= 5:
            score = 1.0
        elif forward_growth >= 0:
            score = 0.0
        else:
            score = -2.0
        components["forward_revenue_growth"] = {"value": forward_growth, "score": score}
        weighted.append((0.5, score))
    else:
        excluded.append("forward_revenue_growth")

    # recommendation mix
    recommendations = expectations.get("recommendations") if isinstance(expectations, dict) else {}
    if isinstance(recommendations, dict):
        values = {}
        for key, val in recommendations.items():
            normalized = str(key).strip().lower().replace(" ", "")
            values[normalized] = safe_numeric(val)
        bullish = sum(v for k, v in values.items() if k in {"strongbuy", "buy"} and v is not None)
        bearish = sum(v for k, v in values.items() if k in {"sell", "strongsell"} and v is not None)
        total = bullish + bearish + sum(v for k, v in values.items() if k == "hold" and v is not None)
        if total and total > 0:
            bullish_share = bullish / total
            bearish_share = bearish / total
            if bullish_share >= 0.60 and bearish_share < 0.15:
                score = 2.0
            elif bullish_share >= 0.50:
                score = 1.0
            elif bearish_share >= 0.50:
                score = -2.0
            elif bearish_share >= 0.15:
                score = -1.0
            else:
                score = 0.0
            components["analyst_recommendation_mix"] = {"value": {"bullish_share": bullish_share, "bearish_share": bearish_share}, "score": score}
            weighted.append((0.25, score))
        else:
            excluded.append("analyst_recommendation_mix")
    else:
        excluded.append("analyst_recommendation_mix")

    # target upside
    price_targets = expectations.get("price_targets") if isinstance(expectations, dict) else {}
    upside = safe_numeric(price_targets.get("implied_upside")) if isinstance(price_targets, dict) else None
    if upside is None:
        upside = safe_numeric(_close_value(expectations, ["implied_upside", "target_upside", "upside"]))
    if upside is not None:
        if upside > 0.20:
            score = 2.0
        elif upside >= 0.05:
            score = 1.0
        elif upside >= -0.05:
            score = 0.0
        elif upside >= -0.20:
            score = -1.0
        else:
            score = -2.0
        components["target_upside"] = {"value": upside, "score": score}
        weighted.append((0.25, score))
    else:
        excluded.append("target_upside")

    if not weighted:
        return unavailable_indicator("Insufficient analyst expectation data.")

    weight_total = sum(weight for weight, _ in weighted)
    aggregate = sum(score * weight for weight, score in weighted) / weight_total if weight_total else 0.0
    if aggregate >= 0.50:
        label = "Positive"
    elif aggregate <= -0.50:
        label = "Negative"
    else:
        label = "Neutral"

    drivers: list[str] = []
    for name, data in sorted(components.items(), key=lambda item: abs(float(item[1].get("score", 0.0))), reverse=True)[:3]:
        score = data.get("score", 0.0)
        if score >= 1:
            drivers.append(f"{name.replace('_', ' ').title()} is bullish.")
        elif score <= -1:
            drivers.append(f"{name.replace('_', ' ').title()} is negative.")
        else:
            drivers.append(f"{name.replace('_', ' ').title()} is neutral.")
    if not drivers:
        drivers = ["Expectations are mixed."]

    evidence = {
        "valid_component_count": len(weighted),
        "total_possible_components": 3,
        "excluded_components": excluded,
    }
    return _standard_indicator(label, aggregate, drivers[:3], components, evidence)


_QUALITATIVE_SCORE_MAP = {
    "risk": {"Low": 0, "Medium": 1, "High": 2},
    "market_environment": {"Unfavourable": -1, "Neutral": 0, "Favourable": 1},
    "competitive_position": {"Weak": -1, "Moderate": 0, "Strong": 1},
}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _latest(value: Any) -> Any:
    return array_first(value)


def _peer_qualitative_context(peer_data: Any, ticker: str | None) -> dict[str, Any]:
    peers = _normalise_dict(peer_data)
    tickers = peers.get("tickers")
    peer_names = [
        str(item).strip()
        for item in tickers
        if isinstance(item, (str, int)) and str(item).strip() and str(item).strip().upper() != (ticker or "").upper()
    ] if isinstance(tickers, list) else []

    notes = _string_list(peers.get("summary"))
    dataframe = peers.get("df")
    if dataframe is not None and hasattr(dataframe, "to_dict"):
        try:
            metric_rows = dataframe.to_dict(orient="index")
        except (TypeError, ValueError):
            metric_rows = {}
        if isinstance(metric_rows, dict):
            for metric, row in metric_rows.items():
                if not isinstance(row, dict):
                    continue
                values = [
                    f"{name}: {numeric}"
                    for name, value in row.items()
                    if str(name).upper() != (ticker or "").upper()
                    and (numeric := safe_numeric(value)) is not None
                ]
                if values:
                    notes.append(f"{metric} — " + "; ".join(values))

    return {"peer_names": peer_names, "peer_notes": notes[:12]}


def build_qualitative_context(context: dict[str, Any]) -> dict[str, Any]:
    """Compact the already-collected company, financial, Feature 9/10, and peer evidence."""
    company = _normalise_dict(context.get("company"))
    financials = _normalise_dict(context.get("financials"))
    ratios = _normalise_dict(context.get("ratios"))
    income = _normalise_dict(financials.get("income"))
    balance = _normalise_dict(financials.get("balance"))
    cashflow = _normalise_dict(financials.get("cashflow"))
    profitability = _normalise_dict(ratios.get("profitability"))
    strength = _normalise_dict(ratios.get("strength"))
    ticker = str(context.get("ticker") or company.get("ticker") or company.get("symbol") or "").strip().upper()

    feature9_result = _normalise_dict(context.get("company_analysis") or context.get("feature9_analysis"))
    feature9 = _normalise_dict(feature9_result.get("analysis")) or feature9_result
    feature10_result = _normalise_dict(context.get("market_review") or context.get("feature10"))
    market_review = _normalise_dict(feature10_result.get("review")) or feature10_result
    market_sources = feature10_result.get("sources")
    sources: list[dict[str, Any]] = []
    if isinstance(market_sources, list):
        for source in market_sources[:6]:
            if not isinstance(source, dict):
                continue
            compact_source = {
                key: source.get(key)
                for key in ("id", "title", "source", "published_at")
                if source.get(key) is not None
            }
            content = source.get("content")
            if isinstance(content, str) and content.strip():
                compact_source["content"] = content.strip()[:600]
            sources.append(compact_source)

    financial_snapshot = {
        "revenue_growth": safe_numeric(_latest(income.get("revenue_growth"))),
        "operating_margin": (
            safe_numeric(_close_value(profitability, ["op_margin", "operating_margin"]))
            if _close_value(profitability, ["op_margin", "operating_margin"]) is not None
            else safe_numeric(_latest(income.get("op_margin")))
        ),
        "free_cash_flow": safe_numeric(_latest(cashflow.get("free_cash_flow"))),
        "debt_to_equity": (
            safe_numeric(_close_value(strength, ["de_ratio", "debt_to_equity"]))
            if _close_value(strength, ["de_ratio", "debt_to_equity"]) is not None
            else safe_numeric(balance.get("de_ratio"))
        ),
    }

    market_context = {
        "industry_summary": market_review.get("industry_overview"),
        "market_growth": market_review.get("market_outlook"),
        "tailwinds": _string_list(market_review.get("growth_drivers")),
        "headwinds": _string_list(market_review.get("industry_risks")),
        "competitive_dynamics": _string_list(market_review.get("competitive_dynamics")),
        "regulatory_environment": market_review.get("regulatory_environment"),
        "macro_exposure": market_review.get("macro_exposure"),
        "sources": sources,
    }
    company_analysis = {
        "business_model": company.get("description"),
        "key_strengths": [
            item for item in (
                feature9.get("financial_performance"),
                feature9.get("peer_positioning"),
            ) if isinstance(item, str) and item.strip()
        ],
        "key_risks": _string_list(feature9.get("key_factors_to_watch")),
        "financial_position": feature9.get("financial_position"),
        "recent_developments": feature9.get("recent_developments"),
    }
    return {
        "ticker": ticker,
        "company": {
            "name": company.get("name"),
            "sector": company.get("sector"),
            "industry": company.get("industry"),
            "description": company.get("description"),
            "country": company.get("country"),
        },
        "financial_snapshot": financial_snapshot,
        "market_review": market_context,
        "company_analysis": company_analysis,
        "peer_context": _peer_qualitative_context(
            context.get("peer_comparison") or context.get("peers"),
            ticker,
        ),
    }


def _has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return value is not None


def _qualitative_evidence_available(qualitative_context: dict[str, Any], key: str) -> bool:
    financial = _normalise_dict(qualitative_context.get("financial_snapshot"))
    company_analysis = _normalise_dict(qualitative_context.get("company_analysis"))
    market = _normalise_dict(qualitative_context.get("market_review"))
    peers = _normalise_dict(qualitative_context.get("peer_context"))

    if key == "risk":
        financial_values = sum(value is not None for value in financial.values())
        return (
            financial_values >= 2
            or _has_content(company_analysis.get("key_risks"))
            or _has_content(market.get("headwinds"))
        )
    if key == "market_environment":
        return any(_has_content(market.get(field)) for field in (
            "industry_summary", "market_growth", "tailwinds", "headwinds", "competitive_dynamics",
        ))
    if key == "competitive_position":
        return (
            _has_content(peers.get("peer_names")) and _has_content(peers.get("peer_notes"))
        ) or _has_content(company_analysis.get("key_strengths"))
    return False


def _qualitative_unavailable(reason: str) -> dict[str, Any]:
    return unavailable_indicator(reason)


def _assess_qualitative_indicators(qualitative_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indicators = {
        key: _qualitative_unavailable("Insufficient evidence from previously collected features.")
        for key in _QUALITATIVE_SCORE_MAP
    }
    eligible = {
        key for key in _QUALITATIVE_SCORE_MAP
        if _qualitative_evidence_available(qualitative_context, key)
    }
    if not eligible:
        return indicators

    try:
        response = gemini_provider.generate_qualitative_assessment(qualitative_context)
    except Exception:
        return indicators
    if not isinstance(response, dict) or response.get("status") != "ok":
        return indicators
    model_indicators = _normalise_dict(response.get("indicators"))

    for key in eligible:
        item = _normalise_dict(model_indicators.get(key))
        label = item.get("label")
        drivers = item.get("drivers")
        evidence = item.get("evidence")
        if not isinstance(label, str) or label not in _QUALITATIVE_SCORE_MAP[key]:
            continue
        if not isinstance(drivers, list) or not 2 <= len(drivers) <= 3:
            continue
        if any(not isinstance(text, str) or not text.strip() for text in drivers):
            continue
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 4:
            continue
        if any(not isinstance(text, str) or not text.strip() for text in evidence):
            continue
        indicators[key] = {
            "label": label,
            "score": _QUALITATIVE_SCORE_MAP[key][label],
            "drivers": [text.strip() for text in drivers],
            "components": {},
            "evidence": [text.strip() for text in evidence],
        }
    return indicators


def build_stock_assessment(context: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Build deterministic Feature 12A indicators and grounded qualitative 12B indicators."""
    if context is None:
        context = kwargs
    elif isinstance(context, dict) and kwargs:
        context = {**context, **kwargs}
    if not isinstance(context, dict):
        return {"status": "ok", "indicators": {}}

    company = context.get("company") or {}
    normalized = {
        "company": company,
        "financials": context.get("financials") or {},
        "ratios": context.get("ratios") or {},
        "valuation": context.get("valuation") or {},
        "performance": context.get("performance") or {},
        "analyst_expectations": context.get("analyst_expectations") or context.get("expectations") or {},
        "peer_comparison": context.get("peer_comparison") or context.get("peers") or {},
        "ticker": context.get("ticker") or context.get("symbol") or company.get("ticker") or company.get("symbol") or None,
    }

    if normalized["ratios"] and not normalized["valuation"]:
        normalized["valuation"] = normalized["ratios"].get("valuation") or {}

    normalized["valuation"] = normalized["valuation"] or {}
    indicators = {
        "valuation": assess_valuation(normalized),
        "financial_quality": assess_financial_quality(normalized),
        "growth": assess_growth(normalized),
        "volatility": assess_volatility(normalized),
        "expectations": assess_expectations(normalized),
    }
    qualitative_context = build_qualitative_context({
        **normalized,
        "company_analysis": context.get("company_analysis") or context.get("feature9_analysis"),
        "market_review": context.get("market_review") or context.get("feature10"),
    })
    indicators.update(_assess_qualitative_indicators(qualitative_context))
    result = {"status": "ok", "indicators": indicators}
    if normalized.get("ticker") is not None:
        result["ticker"] = normalized["ticker"]
    return result


__all__ = [
    "assess_valuation",
    "assess_financial_quality",
    "assess_growth",
    "assess_volatility",
    "assess_expectations",
    "build_qualitative_context",
    "build_stock_assessment",
    "safe_numeric",
    "weighted_average",
    "metric_median",
    "valid_metric_values",
    "unavailable_indicator",
]
