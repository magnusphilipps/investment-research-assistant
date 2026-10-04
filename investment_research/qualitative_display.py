"""Display-safe extraction for the Streamlit qualitative research sections."""

import re
from typing import Any
from urllib.parse import urlparse


MAX_MARKET_SOURCES = 3

COMPANY_SECTIONS = (
    ("Financial Performance", "financial_performance", "text"),
    ("Financial Position", "financial_position", "text"),
    ("Valuation", "valuation", "text"),
    ("Share Price & Expectations", "share_price_and_expectations", "text"),
    ("Peer Positioning", "peer_positioning", "text"),
    ("Recent Developments", "recent_developments", "text"),
    ("Key Factors to Watch", "key_factors_to_watch", "list"),
)

MARKET_SECTIONS = (
    ("Industry Overview", "industry_overview", "text"),
    ("Market Outlook", "market_outlook", "text"),
    ("Growth Drivers", "growth_drivers", "list"),
    ("Competitive Dynamics", "competitive_dynamics", "list"),
    ("Industry Risks", "industry_risks", "list"),
    ("Implications for the Company", "company_implications", "list"),
)

BULL_BEAR_SECTIONS = (
    ("Bull Case", "bull_case"),
    ("Bear Case", "bear_case"),
    ("Key Swing Factors", "swing_factors"),
)

_LOW_VALUE_HOSTS = {"linkedin.com", "wikipedia.org"}
_SOURCE_PRIORITY_TERMS = (
    "news",
    "editorial",
    "journal",
    "research",
    "report",
    "market",
    "industry",
    "outlook",
    "economic",
    "financial",
    "business",
    "analysis",
)
_GENERIC_PAGE_TITLES = {
    "about",
    "about us",
    "company",
    "company overview",
    "homepage",
    "home page",
}
_GENERIC_PAGE_PATHS = {
    "about",
    "about-us",
    "about-the-company",
    "company",
    "company-overview",
}


def _nonempty_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _sanitize_markdown_text(value: str) -> str:
    """Keep narrative in the normal font by escaping math and removing code ticks."""
    return value.replace("`", "").replace("$", r"\$")


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _unavailable_message(result: Any, default: str) -> str:
    if isinstance(result, dict):
        message = _nonempty_text(result.get("message"))
        if message:
            return message
    return default


def _section_items(
    content: dict[str, Any],
    sections: tuple[tuple[str, str, str], ...],
    *,
    hide_market_citations: bool = False,
) -> list[dict[str, Any]]:
    items = []
    for title, key, kind in sections:
        if kind == "text":
            text = _nonempty_text(content.get(key))
            if hide_market_citations:
                text = _hide_market_citations(text)
            if text:
                items.append({
                    "title": title,
                    "kind": "text",
                    "content": _sanitize_markdown_text(text),
                })
        else:
            values = _clean_list(content.get(key))
            if hide_market_citations:
                values = [_hide_market_citations(item) for item in values]
                values = [item for item in values if item]
            if values:
                items.append({
                    "title": title,
                    "kind": "list",
                    "content": [_sanitize_markdown_text(value) for value in values],
                })
    return items


def _hide_market_citations(text: str) -> str:
    without_urls = re.sub(r"https?://\S+", "", text)
    without_markers = re.sub(r"\(?\bS\d+(?:\s*,\s*S\d+)*\)?", "", without_urls)
    return re.sub(r"\s{2,}", " ", without_markers).strip()


def _is_available_result(result: Any, content_key: str) -> tuple[dict[str, Any] | None, bool]:
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None, False
    content = result.get(content_key)
    return (content, True) if isinstance(content, dict) else (None, False)


def get_company_analysis_display(report: Any) -> dict[str, Any]:
    """Return only the user-facing fields from the existing Feature 9 result."""
    result = report.get("company_analysis") if isinstance(report, dict) else None
    analysis, available = _is_available_result(result, "analysis")
    if not available:
        return {
            "available": False,
            "message": _unavailable_message(result, "AI analysis temporarily unavailable."),
            "sections": [],
        }
    return {
        "available": True,
        "message": "",
        "sections": _section_items(analysis, COMPANY_SECTIONS),
    }


def _source_display(source: Any) -> dict[str, str | None] | None:
    if not isinstance(source, dict):
        return None
    title = _nonempty_text(source.get("title"))
    publisher = _nonempty_text(source.get("source"))
    published_at = _nonempty_text(source.get("published_at"))
    raw_url = _nonempty_text(source.get("url"))
    parsed_url = urlparse(raw_url)
    url = raw_url if parsed_url.scheme in {"http", "https"} and parsed_url.netloc else ""
    if not any((title, publisher, published_at, url)):
        return None
    return {
        "title": title,
        "source": publisher,
        "published_at": published_at,
        "url": url or None,
    }


def _source_is_low_value(
    source: dict[str, str | None],
    company_website: str,
) -> bool:
    url = source["url"]
    parsed_url = urlparse(url or "")
    host = (parsed_url.hostname or "").lower().removeprefix("www.")
    identity = " ".join((source["title"] or "", source["source"] or "")).casefold()
    if (
        any(host == domain or host.endswith(f".{domain}") for domain in _LOW_VALUE_HOSTS)
        or any(domain.split(".")[0] in identity for domain in _LOW_VALUE_HOSTS)
    ):
        return True

    path = parsed_url.path.strip("/").lower()
    title = (source["title"] or "").strip().lower()
    generic_page = title in _GENERIC_PAGE_TITLES or path in _GENERIC_PAGE_PATHS or not path
    if not generic_page:
        return False

    website_host = (urlparse(company_website).hostname or "").lower().removeprefix("www.")
    same_company_site = bool(
        website_host
        and host
        and (host == website_host or host.endswith(f".{website_host}") or website_host.endswith(f".{host}"))
    )
    return same_company_site or path in _GENERIC_PAGE_PATHS or (not path and title in _GENERIC_PAGE_TITLES)


def _source_priority(source: dict[str, str | None]) -> int:
    searchable = " ".join(
        value or ""
        for value in (source["title"], source["source"], source["url"])
    ).casefold()
    return sum(term in searchable for term in _SOURCE_PRIORITY_TERMS)


def get_market_review_display(report: Any) -> dict[str, Any]:
    """Return the validated Feature 10 review and compact source labels."""
    result = report.get("market_review") if isinstance(report, dict) else None
    review, available = _is_available_result(result, "review")
    if not available:
        return {
            "available": False,
            "message": _unavailable_message(
                result,
                "Market & industry review temporarily unavailable.",
            ),
            "sections": [],
            "sources": [],
        }

    raw_sources = result.get("sources") if isinstance(result, dict) else None
    company = report.get("company") if isinstance(report, dict) else None
    company_website = _nonempty_text(company.get("website")) if isinstance(company, dict) else ""
    candidates = []
    if isinstance(raw_sources, list):
        for index, source in enumerate(raw_sources):
            item = _source_display(source)
            if item is None or _source_is_low_value(item, company_website):
                continue
            candidates.append((index, item))
    candidates.sort(key=lambda candidate: (-_source_priority(candidate[1]), candidate[0]))
    sources = [item for _, item in candidates[:MAX_MARKET_SOURCES]]
    return {
        "available": True,
        "message": "",
        "sections": _section_items(
            review,
            MARKET_SECTIONS,
            hide_market_citations=True,
        ),
        "sources": sources,
    }


def get_bull_bear_display(report: Any) -> dict[str, Any]:
    """Return only the three user-facing Feature 11 scenario lists."""
    result = report.get("bull_bear") if isinstance(report, dict) else None
    analysis, available = _is_available_result(result, "analysis")
    if not available:
        return {
            "available": False,
            "message": _unavailable_message(
                result,
                "Bull / Bear analysis temporarily unavailable.",
            ),
            "sections": [],
        }
    sections = []
    for title, key in BULL_BEAR_SECTIONS:
        items = _clean_list(analysis.get(key))
        if items:
            sections.append({
                "title": title,
                "kind": "list",
                "content": [_sanitize_markdown_text(item) for item in items],
            })
    return {"available": True, "message": "", "sections": sections}
