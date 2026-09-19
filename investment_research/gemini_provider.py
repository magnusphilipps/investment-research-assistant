"""
gemini_provider.py — Gemini-specific Feature 9 integration.

Only this module knows about the Google Gemini SDK. Keeping that dependency
here makes a future Claude/OpenAI provider swap local to one module.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from . import cache


MODEL_NAME = "gemini-3.6-flash"
UNAVAILABLE_MESSAGE = "AI analysis temporarily unavailable."
MARKET_UNAVAILABLE_MESSAGE = "Market & industry review temporarily unavailable."

SYSTEM_INSTRUCTION = """
You are a neutral educational equity-research analyst.

Use ONLY the supplied company-specific evidence when making factual claims.
Do not invent financial figures, news, analyst forecasts, peer metrics, or
outside company facts. Missing or null evidence means the information is
unavailable; it does not mean zero. Distinguish factual observations from
your analytical interpretation.

Interpret relationships between the supplied metrics instead of simply
repeating every number. Highlight material strengths, weaknesses, trends, and
tensions in the evidence. Be concise and selective, use a neutral professional
research style, and do not provide personalized financial advice.

Do not produce a Buy, Hold, or Sell recommendation. Do not generate an
unsupported price target. Recent news is evidence for developments only; do
not add sentiment scoring.

Return only the requested JSON structure.
""".strip()


ANALYSIS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "financial_performance": {"type": "STRING"},
        "financial_position": {"type": "STRING"},
        "valuation": {"type": "STRING"},
        "share_price_and_expectations": {"type": "STRING"},
        "peer_positioning": {"type": "STRING"},
        "recent_developments": {"type": "STRING"},
        "key_factors_to_watch": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "minItems": 3,
            "maxItems": 5,
        },
    },
    "required": [
        "financial_performance",
        "financial_position",
        "valuation",
        "share_price_and_expectations",
        "peer_positioning",
        "recent_developments",
        "key_factors_to_watch",
    ],
}

MARKET_REVIEW_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "industry_overview": {"type": "STRING"},
        "growth_drivers": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 5},
        "competitive_dynamics": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 5},
        "industry_risks": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 5},
        "market_outlook": {"type": "STRING"},
        "company_implications": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 5},
        "sources_used": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 1},
    },
    "required": [
        "industry_overview", "growth_drivers", "competitive_dynamics",
        "industry_risks", "market_outlook", "company_implications", "sources_used",
    ],
}

PEER_DISCOVERY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "peers": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "ticker": {"type": "STRING"},
                    "company_name": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": ["ticker", "company_name", "reason"],
            },
            "minItems": 1,
            "maxItems": 5,
        },
    },
    "required": ["peers"],
}

BULL_BEAR_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "bull_case": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 3},
        "bear_case": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 3},
        "swing_factors": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 3},
    },
    "required": ["bull_case", "bear_case", "swing_factors"],
}

_TEXT_FIELDS = (
    "financial_performance",
    "financial_position",
    "valuation",
    "share_price_and_expectations",
    "peer_positioning",
    "recent_developments",
)


def _unavailable() -> dict[str, Any]:
    """Return the stable public failure shape without provider details."""
    return {
        "status": "unavailable",
        "message": UNAVAILABLE_MESSAGE,
        "analysis": None,
    }


def _validate_analysis(value: Any) -> dict[str, Any] | None:
    """Validate the model's decoded structured response before display."""
    if not isinstance(value, dict):
        return None

    analysis: dict[str, Any] = {}
    for field in _TEXT_FIELDS:
        text = value.get(field)
        if not isinstance(text, str) or not text.strip():
            return None
        analysis[field] = text.strip()

    factors = value.get("key_factors_to_watch")
    if not isinstance(factors, list) or not 3 <= len(factors) <= 5:
        return None
    if any(not isinstance(factor, str) or not factor.strip() for factor in factors):
        return None
    analysis["key_factors_to_watch"] = [factor.strip() for factor in factors]
    return analysis


def _is_503(error: Exception) -> bool:
    text = str(error).lower()
    return "503" in text or "service unavailable" in text or "high demand" in text or "unavailable" in text


def _is_429(error: Exception) -> bool:
    text = str(error).lower()
    return "429" in text or "resource_exhausted" in text or "quota" in text or "rate limit" in text


def _request_with_retry(request, feature_label: str) -> str | None:
    for attempt in range(3):
        try:
            return request()
        except Exception as exc:
            if _is_429(exc):
                print(f"{feature_label}: Gemini quota or rate limit reached.")
            elif _is_503(exc) and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            else:
                print(f"{feature_label} ERROR:", repr(exc))
            return None
    return None


def _request_model(context: dict[str, Any], api_key: str) -> str:
    """Call Gemini using the current official Google Python SDK."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=(
            "Analyse the following structured company evidence. "
            "Do not use outside knowledge.\n\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        ),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=ANALYSIS_SCHEMA,
        ),
    )
    return str(getattr(response, "text", "") or "")


def generate_analysis(context: dict[str, Any]) -> dict[str, Any]:
    """
    Generate grounded analysis or a safe unavailable result.

    The API key is read only from the Replit Secret-backed environment variable
    ``GOOGLE_API_KEY`` and is never included in errors or returned data.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return _unavailable()

    cached = cache.read("feature-9", context)
    if isinstance(cached, dict) and cached.get("status") == "ok":
        cached_analysis = _validate_analysis(cached.get("analysis"))
        if cached_analysis is not None:
            return {"status": "ok", "message": None, "analysis": cached_analysis}

    raw_response = _request_with_retry(
        lambda: _request_model(context, api_key),
        "FEATURE 9",
    )
    if not raw_response or not raw_response.strip():
        return _unavailable()
    try:
        decoded = json.loads(raw_response)
    except (TypeError, ValueError):
        return _unavailable()
    analysis = _validate_analysis(decoded)
    if analysis is None:
        return _unavailable()

    result = {
        "status": "ok",
        "message": None,
        "analysis": analysis,
    }
    try:
        cache.write("feature-9", context, result)
    except (OSError, TypeError, ValueError):
        pass
    return result


def _validate_market_review(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    text_fields = ("industry_overview", "market_outlook")
    list_fields = ("growth_drivers", "competitive_dynamics", "industry_risks", "company_implications")
    result: dict[str, Any] = {}
    for field in text_fields:
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            return None
        result[field] = item.strip()
    for field in list_fields:
        items = value.get(field)
        if not isinstance(items, list) or not 3 <= len(items) <= 5:
            return None
        if any(not isinstance(item, str) or not item.strip() for item in items):
            return None
        result[field] = [item.strip() for item in items]
    sources = value.get("sources_used")
    if not isinstance(sources, list) or not sources or any(
        not isinstance(item, str) or not item.strip() for item in sources
    ):
        return None
    result["sources_used"] = list(dict.fromkeys(item.strip() for item in sources))
    return result


def _validate_peer_candidates(value: Any) -> list[dict[str, str]] | None:
    if not isinstance(value, dict):
        return None
    candidates = value.get("peers")
    if not isinstance(candidates, list) or not candidates:
        return None
    result: list[dict[str, str]] = []
    for item in candidates:
        if not isinstance(item, dict):
            return None
        ticker = item.get("ticker")
        company_name = item.get("company_name")
        reason = item.get("reason")
        if not isinstance(ticker, str) or not ticker.strip():
            return None
        if not isinstance(company_name, str) or not company_name.strip():
            return None
        if not isinstance(reason, str) or not reason.strip():
            return None
        result.append({
            "ticker": ticker.strip().upper(),
            "company_name": company_name.strip(),
            "reason": reason.strip(),
        })
    return result[:5]


def _request_market_model(context: dict[str, Any], api_key: str) -> str:
    """Call Gemini with only the compact external evidence package."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=(
            "Produce a market and industry review from the supplied evidence. "
            "Use only evidence content and company metadata provided here. "
            "Use the supplied research_focus as the primary economic lens. "
            "Prefer the narrowest meaningful industry and relevant value chain; "
            "do not fall back to broad sector commentary when the focus is available. "
            "Use evidence IDs such as S1 in sources_used; never invent URLs or IDs. "
            "Do not put source IDs, URLs, source names, or citation markers in the "
            "narrative fields. If sources give materially different market-size "
            "estimates, do not combine them into a range or average them. Prefer the "
            "most credible directly relevant evidence, or omit precise figures and "
            "describe only the supported direction or magnitude. Never invent why "
            "estimates differ. Prioritize developments with a clear external "
            "development -> business mechanism -> potential company implication. "
            "If evidence is limited, say so. Do not provide an investment recommendation.\n\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        ),
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a neutral market-research analyst. Use ONLY supplied evidence "
                "and the supplied research_focus for factual claims. Treat research_focus "
                "as a query lens, not as proof of a fact. Prefer the narrowest meaningful "
                "industry, value chain, and external drivers material to this company. "
                "Deprioritize broad sector statistics and unrelated subsectors. "
                "Do not invent market sizes, growth rates, competitors, "
                "regulation, forecasts, dates, trends, or company implications. Distinguish "
                "facts from interpretation and use cautious language such as may, could, "
                "creates potential for, increases exposure to, and represents a risk to. "
                "State causal relationships only when the evidence supports them. Do not "
                "combine or average materially incompatible market-size estimates; omit "
                "precise figures when they cannot be reconciled. Prioritize evidence that "
                "could affect demand, growth, margins, pricing, competition, market share, "
                "supply, capital needs, regulation, or execution. Do not put source IDs, "
                "URLs, source names, or citation markers in narrative fields. Return only "
                "the requested JSON structure."
            ),
            temperature=0.2,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=MARKET_REVIEW_SCHEMA,
        ),
    )
    return str(getattr(response, "text", "") or "")


def _request_peer_model(context: dict[str, Any], api_key: str) -> str:
    """Ask Gemini for candidate peers using only supplied company metadata."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=(
            "Propose 5 public-company peer candidates for the target company using only the supplied metadata. "
            "Do not calculate financial metrics, do not decide the final peer set, and do not invent data. "
            "Return only a JSON object with a 'peers' array of candidate objects containing ticker, company_name, and reason.\n\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        ),
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a disciplined equity-research analyst. Use only the supplied company metadata. "
                "Prefer economically similar public companies, not just broad sector matches. Prioritize core business model, products, end markets, customer base, revenue drivers, competitive set, geography, and scale where relevant. Avoid private companies, subsidiaries, ETFs, shell companies, invalid tickers, suppliers/customers unless they are genuine competitors, conglomerates with unrelated economics, and companies with clearly different business models. Return only the requested JSON structure."
            ),
            temperature=0.2,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=PEER_DISCOVERY_SCHEMA,
        ),
    )
    return str(getattr(response, "text", "") or "")


def generate_peer_candidates(context: dict[str, Any]) -> dict[str, Any]:
    """Generate or return a safe unavailable result for peer discovery."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"status": "unavailable", "message": "Peer discovery temporarily unavailable.", "peers": []}

    cached = cache.read("feature-7-peers", context)
    if isinstance(cached, dict) and cached.get("status") == "ok":
        cached_peers = _validate_peer_candidates(cached)
        if cached_peers is not None:
            return {"status": "ok", "message": None, "peers": cached_peers}

    raw_response = _request_with_retry(
        lambda: _request_peer_model(context, api_key),
        "FEATURE 7",
    )
    if not raw_response or not raw_response.strip():
        return {"status": "unavailable", "message": "Peer discovery temporarily unavailable.", "peers": []}

    try:
        parsed_response = json.loads(raw_response)
    except (TypeError, ValueError):
        return {"status": "unavailable", "message": "Peer discovery temporarily unavailable.", "peers": []}

    peers = _validate_peer_candidates(parsed_response)
    if peers is None:
        return {"status": "unavailable", "message": "Peer discovery temporarily unavailable.", "peers": []}

    result = {"status": "ok", "message": None, "peers": peers}
    try:
        cache.write("feature-7-peers", context, result)
    except (OSError, TypeError, ValueError):
        pass
    return result


def generate_market_review(context: dict[str, Any]) -> dict[str, Any]:
    """Generate a validated grounded market review or a safe unavailable result."""
    api_key = os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        return {
            "status": "unavailable",
            "message": MARKET_UNAVAILABLE_MESSAGE,
            "review": None,
        }

    cached = cache.read("feature-10", context)
    if isinstance(cached, dict) and cached.get("status") == "ok":
        cached_review = _validate_market_review(cached.get("review"))
        if cached_review is not None:
            return {"status": "ok", "message": None, "review": cached_review}

    raw_response = _request_with_retry(
        lambda: _request_market_model(context, api_key),
        "FEATURE 10",
    )
    if not raw_response:
        return {
            "status": "unavailable",
            "message": MARKET_UNAVAILABLE_MESSAGE,
            "review": None,
        }

    if not raw_response.strip():
        return {
            "status": "unavailable",
            "message": MARKET_UNAVAILABLE_MESSAGE,
            "review": None,
        }

    try:
        parsed_response = json.loads(raw_response)
    except (TypeError, ValueError):
        return {
            "status": "unavailable",
            "message": MARKET_UNAVAILABLE_MESSAGE,
            "review": None,
        }
    review = _validate_market_review(parsed_response)

    if review is None:
        return {
            "status": "unavailable",
            "message": MARKET_UNAVAILABLE_MESSAGE,
            "review": None,
        }

    result = {
        "status": "ok",
        "message": None,
        "review": review,
    }
    try:
        cache.write("feature-10", context, result)
    except (OSError, TypeError, ValueError):
        pass
    return result


def _validate_bull_bear(value: Any) -> dict[str, list[str]] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, list[str]] = {}
    for field in ("bull_case", "bear_case"):
        items = value.get(field)
        if not isinstance(items, list) or len(items) != 3:
            return None
        if any(
            not isinstance(item, str)
            or not item.strip()
            or not 10 <= len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", item)) <= 16
            or len(re.findall(r"[.!?]", item)) != 1
            or item.rstrip()[-1] not in ".!?"
            for item in items
        ):
            return None
        result[field] = [item.strip() for item in items]
    items = value.get("swing_factors")
    if not isinstance(items, list) or len(items) != 3:
        return None
    if any(
        not isinstance(item, str)
        or not item.strip()
        or not 4 <= len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", item)) <= 10
        or re.search(r"[.!?]", item)
        for item in items
    ):
        return None
    result["swing_factors"] = [item.strip() for item in items]
    return result


def _request_bull_bear_model(context: dict[str, Any], api_key: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=(
            "Create exactly three conditional bull-case arguments, three conditional "
            "bear-case arguments, and three concise swing factors from ONLY this evidence. "
            "Bull and bear items must be exactly one sentence and 10-16 words, using "
            "one clear evidence -> business mechanism -> potential implication. "
            "Swing factors must be 4-10 words, phrased only as variables to monitor. "
            "Do not use analyst forecasts or metrics as the mechanism itself; use the "
            "underlying demand, pricing, competition, capacity, execution, or financial "
            "driver, with forecasts only as supporting evidence. Avoid subordinate clauses, "
            "deterministic claims, excessive numbers, recommendations, and target prices. "
            "Use cautious wording such as could, may, or increases exposure to. "
            "Every bull/bear item must end with one sentence-ending punctuation mark; "
            "swing factors must not be sentences. Do not provide outside facts.\n\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        ),
        config=types.GenerateContentConfig(
            system_instruction="Return only the requested grounded JSON structure.",
            temperature=0.2,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=BULL_BEAR_SCHEMA,
        ),
    )
    return str(getattr(response, "text", "") or "")


def generate_bull_bear(context: dict[str, Any]) -> dict[str, Any]:
    """Generate validated Feature 11 scenario analysis or a safe unavailable result."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"status": "unavailable", "message": "Bull / Bear analysis temporarily unavailable.", "analysis": None}
    raw_response = _request_with_retry(lambda: _request_bull_bear_model(context, api_key), "FEATURE 11")
    if not raw_response:
        return {"status": "unavailable", "message": "Bull / Bear analysis temporarily unavailable.", "analysis": None}
    try:
        analysis = _validate_bull_bear(json.loads(raw_response))
    except (TypeError, ValueError):
        analysis = None
    if analysis is None:
        return {"status": "unavailable", "message": "Bull / Bear analysis temporarily unavailable.", "analysis": None}
    return {"status": "ok", "message": None, "analysis": analysis}