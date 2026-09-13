"""Provider-neutral Feature 10 research orchestration and evidence handling."""

from __future__ import annotations

from datetime import date
import re
from typing import Any
from urllib.parse import urlparse

from . import gemini_provider, tavily_provider


MAX_QUERIES = 5
MAX_EVIDENCE = 12
MAX_CONTENT_CHARACTERS = 1800
UNAVAILABLE_MESSAGE = "Market & industry review temporarily unavailable."

_DESCRIPTION_MARKETS = (
    (
        re.compile(
            r"\b(?:"
            r"ai infrastructure|infrastructure for ai|"
            r"gpu cloud|gpu clusters?|accelerated computing|"
            r"data cent(?:er|re)|cloud computing|cloud platforms?"
            r"|tools and services for developers"
            r")\b",
            re.I,
        ),
        "AI infrastructure and GPU cloud",
        "chips, networking, data centers, power, and cloud capacity",
        "AI infrastructure spending, accelerator demand, capacity, power constraints, competition, and regulation",
    ),
    (
        re.compile(r"\b(?:rare earth|ndpr|permanent magnet|magnet manufacturing)\b", re.I),
        "rare earths, NdPr materials, and permanent magnets",
        "mining, separation, refining, and magnet manufacturing",
        "EV, robotics, industrial and strategic demand, supply concentration, localization, pricing, policy, and competing capacity",
    ),
    (
        re.compile(r"\b(?:smartphone|personal computing|wearable|digital ecosystem)\b", re.I),
        "smartphones, personal computing, wearables, and digital ecosystems",
        "components, manufacturing, distribution, platforms, and services",
        "device demand, replacement cycles, component costs, supply concentration, competition, regulation, and services monetization",
    ),
    (
        re.compile(r"\b(?:banking|lending|deposit|capital market|investment bank|payments)\b", re.I),
        "large-bank lending, payments, and capital markets",
        "deposits, lending, payments, investment banking, markets, and regulation",
        "interest rates, credit conditions, deposit competition, capital requirements, market activity, regulation, and economic conditions",
    ),
)


def _clean_text(value: Any) -> str:
    return " ".join(value.split()).strip() if isinstance(value, str) else ""


def build_research_focus(stock_info: dict[str, Any] | None) -> dict[str, Any]:
    """Identify the narrowest practical economic lens available for a company."""
    info = stock_info if isinstance(stock_info, dict) else {}
    industry = _clean_text(info.get("industry"))
    sector = _clean_text(info.get("sector"))
    description = _clean_text(info.get("description"))
    markets = []
    for pattern, market, value_chain, drivers in _DESCRIPTION_MARKETS:
        if pattern.search(description):
            markets.append({
                "market": market,
                "value_chain": value_chain,
                "drivers": drivers,
            })

    if markets:
        return {
            "industry": "; ".join(item["market"] for item in markets[:4]),
            "value_chain": "; ".join(item["value_chain"] for item in markets[:4]),
            "drivers": "; ".join(item["drivers"] for item in markets[:4]),
            "markets": markets[:4],
        }

    name = _clean_text(info.get("name"))
    ticker = _clean_text(info.get("ticker"))
    subject = industry or sector or name or ticker
    return {
        "industry": subject,
        "value_chain": f"the relevant {subject} supply chain, distribution, and customers",
        "drivers": (
            f"demand, pricing, competition, supply availability, regulation, capital needs, "
            f"and execution in {subject}"
        ),
        "description_context": description[:500],
        "markets": [{"market": subject}] if subject else [],
    }


def build_queries(stock_info: dict[str, Any] | None) -> list[str]:
    """Build deterministic queries around the company's narrow economic lens."""
    info = stock_info if isinstance(stock_info, dict) else {}
    name = _clean_text(info.get("name"))
    ticker = _clean_text(info.get("ticker"))
    focus = build_research_focus(info)
    subject = focus.get("industry", "")
    if not subject:
        return []
    year = date.today().year
    company = name or ticker
    value_chain = focus["value_chain"]
    drivers = focus["drivers"]
    return [
        f"{subject} demand growth pricing outlook {year}",
        f"{subject} value chain {value_chain} supply capacity {year}",
        f"{subject} competition technology customers market share {year}",
        f"{subject} regulation policy risks capital requirements {year}",
        f"{company} {subject} external drivers {drivers} {year}",
    ][:MAX_QUERIES]


def _valid_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _clean_content(value: Any) -> str:
    text = _clean_text(value)
    if len(text) <= MAX_CONTENT_CHARACTERS:
        return text
    shortened = text[:MAX_CONTENT_CHARACTERS].rsplit(" ", 1)[0].rstrip(" ,;:")
    return shortened or text[:MAX_CONTENT_CHARACTERS]


def clean_evidence(raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep compact, source-preserving evidence and remove duplicate articles."""
    evidence: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for result in raw_results:
        if not isinstance(result, dict):
            continue
        title = _clean_text(result.get("title"))
        url = _valid_url(result.get("url"))
        content = _clean_content(result.get("content") or result.get("raw_content"))
        if not title or not url or not content:
            continue
        title_key = re.sub(r"\W+", " ", title.casefold()).strip()
        if url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        evidence.append({
            "id": f"S{len(evidence) + 1}",
            "title": title,
            "source": _clean_text(result.get("source"))
            or urlparse(url).netloc.removeprefix("www."),
            "url": url,
            "published_at": result.get("published_date") or result.get("published_at"),
            "content": content,
            "relevance_score": result.get("score"),
        })
        if len(evidence) >= MAX_EVIDENCE:
            break
    return evidence


def _unavailable() -> dict[str, Any]:
    return {"status": "unavailable", "message": UNAVAILABLE_MESSAGE, "review": None, "sources": []}


def _validate_review(review: Any, evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(review, dict):
        return None
    text_fields = ("industry_overview", "market_outlook")
    list_fields = ("growth_drivers", "competitive_dynamics", "industry_risks", "company_implications")
    validated: dict[str, Any] = {}
    for field in text_fields:
        value = review.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
        validated[field] = value.strip()
    for field in list_fields:
        values = review.get(field)
        if not isinstance(values, list) or not 3 <= len(values) <= 5:
            return None
        if any(not isinstance(item, str) or not item.strip() for item in values):
            return None
        validated[field] = [item.strip() for item in values]
    valid_ids = {item["id"] for item in evidence}
    sources_used = review.get("sources_used")
    if not isinstance(sources_used, list) or not sources_used:
        return None
    if any(not isinstance(source_id, str) or source_id not in valid_ids for source_id in sources_used):
        return None
    validated["sources_used"] = list(dict.fromkeys(sources_used))
    return validated


def get_market_review(stock_info: dict[str, Any] | None) -> dict[str, Any]:
    """Retrieve external evidence and synthesize a grounded market review."""
    queries = build_queries(stock_info)
    if not queries:
        return _unavailable()

    raw_results: list[dict[str, Any]] = []
    try:
        for query in queries:
            raw_results.extend(tavily_provider.search(query))
    except Exception:
        return _unavailable()

    evidence = clean_evidence(raw_results)
    if not evidence:
        return _unavailable()

    context = {
        "company": {
            key: (stock_info or {}).get(key)
            for key in ("ticker", "name", "sector", "industry", "country", "description")
        },
        "research_focus": build_research_focus(stock_info),
        "evidence": evidence,
    }
    try:
        result = gemini_provider.generate_market_review(context)
    except Exception:
        return _unavailable()
    if result.get("status") != "ok":
        return _unavailable()
    review = _validate_review(result.get("review"), evidence)
    if review is None:
        return _unavailable()
    source_ids = set(review["sources_used"])
    return {
        "status": "ok",
        "message": None,
        "review": review,
        "sources": [source for source in evidence if source["id"] in source_ids],
    }
