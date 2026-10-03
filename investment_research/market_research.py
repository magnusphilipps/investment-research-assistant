"""Provider-neutral Feature 10 research orchestration and evidence handling."""

from __future__ import annotations

from datetime import date
import logging
import re
from typing import Any
from urllib.parse import urlparse

from . import cache, gemini_provider, tavily_provider
from .assessment_scoring import is_concise_bullet


MAX_QUERIES = 1
MAX_EVIDENCE = 8
MAX_CONTENT_CHARACTERS = 1800
UNAVAILABLE_MESSAGE = "Market & industry review temporarily unavailable."
LOGGER = logging.getLogger(__name__)

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
            "drivers": (
                "; ".join(item["drivers"] for item in markets[:4])
                + "; customer adoption and preferences, product-market fit, "
                "commercialization, regulatory acceptance, and demand-side barriers"
            ),
            "markets": markets[:4],
        }

    name = _clean_text(info.get("name"))
    ticker = _clean_text(info.get("ticker"))
    subject = industry or sector or name or ticker
    return {
        "industry": subject,
        "value_chain": f"the relevant {subject} supply chain, distribution, and customers",
        "drivers": (
            f"demand, customer adoption and preferences, product-market fit, "
            f"commercialization, regulation, demand-side barriers, pricing, competition, "
            f"supply availability, capital needs, and execution in {subject}"
        ),
        "description_context": description[:500],
        "markets": [{"market": subject}] if subject else [],
    }


def build_queries(stock_info: dict[str, Any] | None) -> list[str]:
    """Build one broad, deterministic query around the company's economic lens."""
    info = stock_info if isinstance(stock_info, dict) else {}
    name = _clean_text(info.get("name"))
    ticker = _clean_text(info.get("ticker")).upper()
    sector = _clean_text(info.get("sector"))
    country = _clean_text(info.get("country"))
    focus = build_research_focus(info)
    subject = focus.get("industry", "")
    if not subject:
        return []
    year = date.today().year
    identity = " ".join(part for part in (name, f"({ticker})" if ticker else "") if part)
    market = " ".join(part for part in (subject, sector, country) if part)
    query = (
        f"{identity} {market} market outlook demand growth value chain supply "
        f"capacity customer adoption preferences product-market fit commercialization "
        f"competition pricing regulation policy macro risks company implications {year}"
    )
    return [query][:MAX_QUERIES]


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


def _market_cache_context(stock_info: dict[str, Any] | None, query: str) -> dict[str, Any]:
    info = stock_info if isinstance(stock_info, dict) else {}
    return {
        "ticker": _clean_text(info.get("ticker")).upper(),
        "name": _clean_text(info.get("name")),
        "sector": _clean_text(info.get("sector")),
        "industry": _clean_text(info.get("industry")),
        "country": _clean_text(info.get("country")),
        "research_focus": build_research_focus(info),
        "query": query,
    }


def _validate_cached_result(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("status") != "ok":
        return None
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        return None
    normalized_sources = []
    for source in sources:
        if not isinstance(source, dict):
            return None
        source_id = source.get("id")
        title = _clean_text(source.get("title"))
        url = _valid_url(source.get("url"))
        content = _clean_content(source.get("content"))
        if (
            not isinstance(source_id, str)
            or not re.fullmatch(r"S\d+", source_id)
            or not title
            or not url
            or not content
        ):
            return None
        normalized_sources.append({
            **source,
            "id": source_id,
            "title": title,
            "source": _clean_text(source.get("source"))
            or urlparse(url).netloc.removeprefix("www."),
            "url": url,
            "content": content,
        })
    if not normalized_sources:
        return None
    review = _validate_review(value.get("review"), normalized_sources)
    if review is None:
        return None
    used_ids = set(review["sources_used"])
    return {
        "status": "ok",
        "message": None,
        "review": review,
        "sources": [source for source in normalized_sources if source["id"] in used_ids],
    }


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
        if any(not is_concise_bullet(item) for item in values):
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

    query = queries[0]
    cache_context = _market_cache_context(stock_info, query)
    cached = cache.read("feature-10-market-review", cache_context)
    if cached is not None:
        valid_cached = _validate_cached_result(cached)
        if valid_cached is not None:
            LOGGER.debug("Feature 10 cache hit; Tavily searches=0")
            return valid_cached

    LOGGER.debug("Feature 10 cache miss; Tavily search count=1")
    try:
        raw_results = tavily_provider.search(
            query, max_results=tavily_provider.MAX_RESULTS_PER_QUERY, search_depth="basic"
        )
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
    final_result = {
        "status": "ok",
        "message": None,
        "review": review,
        "sources": [source for source in evidence if source["id"] in source_ids],
    }
    try:
        cache.write("feature-10-market-review", cache_context, final_result)
    except (OSError, TypeError, ValueError):
        pass
    return final_result
