"""
gemini_provider.py — Gemini-specific Feature 9 integration.

Only this module knows about the Google Gemini SDK. Keeping that dependency
here makes a future Claude/OpenAI provider swap local to one module.
"""

from __future__ import annotations

import json
import os
from typing import Any


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

    try:
        raw_response = _request_model(context, api_key)
        if not raw_response.strip():
            return _unavailable()
        decoded = json.loads(raw_response)
        analysis = _validate_analysis(decoded)
        if analysis is None:
            return _unavailable()
    except Exception:
        # Provider errors, rate limits, malformed JSON, and SDK failures are
        # deliberately hidden behind the same user-friendly result.
        return _unavailable()

    return {
        "status": "ok",
        "message": None,
        "analysis": analysis,
    }


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


def generate_market_review(context: dict[str, Any]) -> dict[str, Any]:
    """Generate a validated grounded market review or a safe unavailable result."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"status": "unavailable", "message": MARKET_UNAVAILABLE_MESSAGE, "review": None}
    try:
        raw_response = _request_market_model(context, api_key)
        if not raw_response.strip():
            return {"status": "unavailable", "message": MARKET_UNAVAILABLE_MESSAGE, "review": None}
        review = _validate_market_review(json.loads(raw_response))
    except Exception:
        return {"status": "unavailable", "message": MARKET_UNAVAILABLE_MESSAGE, "review": None}
    if review is None:
        return {"status": "unavailable", "message": MARKET_UNAVAILABLE_MESSAGE, "review": None}
    return {"status": "ok", "message": None, "review": review}