"""
gemini_provider.py — Gemini-specific Feature 9 integration.

Only this module knows about the Google Gemini SDK. Keeping that dependency
here makes a future Claude/OpenAI provider swap local to one module.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from . import cache
from .assessment_scoring import is_concise_bullet, validate_qualitative_indicator


logger = logging.getLogger(__name__)
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

Treat a structured pre-revenue status as distinct from ordinary low growth.
Do not use metrics explicitly marked not_meaningful as evidence of growth or
valuation.
For dashboard bullets, express one idea in roughly 10–14 words and no more
than 90 characters. Do not truncate a thought to meet the limit.

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
            "items": {"type": "STRING", "maxLength": 90},
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
        "growth_drivers": {"type": "ARRAY", "items": {"type": "STRING", "maxLength": 90}, "minItems": 3, "maxItems": 5},
        "competitive_dynamics": {"type": "ARRAY", "items": {"type": "STRING", "maxLength": 90}, "minItems": 3, "maxItems": 5},
        "industry_risks": {"type": "ARRAY", "items": {"type": "STRING", "maxLength": 90}, "minItems": 3, "maxItems": 5},
        "market_outlook": {"type": "STRING"},
        "company_implications": {"type": "ARRAY", "items": {"type": "STRING", "maxLength": 90}, "minItems": 3, "maxItems": 5},
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
        "bull_case": {
            "type": "ARRAY",
            "items": {"type": "STRING", "minLength": 1, "maxLength": 110},
            "minItems": 3,
            "maxItems": 3,
            "description": (
                "Exactly 3 non-empty strings; each 10-16 words and at most 110 "
                "characters including spaces and punctuation. Target 90-100 "
                "characters. Exactly one sentence-ending punctuation mark."
            ),
        },
        "bear_case": {
            "type": "ARRAY",
            "items": {"type": "STRING", "minLength": 1, "maxLength": 110},
            "minItems": 3,
            "maxItems": 3,
            "description": (
                "Exactly 3 non-empty strings; each 10-16 words and at most 110 "
                "characters including spaces and punctuation. Target 90-100 "
                "characters. Exactly one sentence-ending punctuation mark."
            ),
        },
        "swing_factors": {
            "type": "ARRAY",
            "items": {"type": "STRING", "minLength": 1, "maxLength": 90},
            "minItems": 3,
            "maxItems": 3,
            "description": (
                "Exactly 3 non-empty strings; each 4-10 words, at most 90 "
                "characters, with no period, exclamation mark, or question mark."
            ),
        },
    },
    "required": ["bull_case", "bear_case", "swing_factors"],
}

QUALITATIVE_ASSESSMENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "risk": {
            "type": "OBJECT",
            "properties": {
                "label": {"type": "STRING", "enum": ["Low", "Medium", "High"]},
                "drivers": {
                    "type": "ARRAY",
                    "items": {"type": "STRING", "maxLength": 90},
                    "minItems": 2,
                    "maxItems": 3,
                    "description": "Each driver is one sentence, at most 14 words and 90 characters.",
                },
                "evidence": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 1, "maxItems": 4},
            },
            "required": ["label", "drivers", "evidence"],
        },
        "market_environment": {
            "type": "OBJECT",
            "properties": {
                "label": {"type": "STRING", "enum": ["Unfavourable", "Neutral", "Favourable"]},
                "drivers": {
                    "type": "ARRAY",
                    "items": {"type": "STRING", "maxLength": 90},
                    "minItems": 2,
                    "maxItems": 3,
                    "description": "Each driver is one sentence, at most 14 words and 90 characters.",
                },
                "evidence": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 1, "maxItems": 4},
            },
            "required": ["label", "drivers", "evidence"],
        },
        "competitive_position": {
            "type": "OBJECT",
            "properties": {
                "label": {"type": "STRING", "enum": ["Weak", "Moderate", "Strong"]},
                "drivers": {
                    "type": "ARRAY",
                    "items": {"type": "STRING", "maxLength": 90},
                    "minItems": 2,
                    "maxItems": 3,
                    "description": "Each driver is one sentence, at most 14 words and 90 characters.",
                },
                "evidence": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 1, "maxItems": 4},
            },
            "required": ["label", "drivers", "evidence"],
        },
    },
    "required": ["risk", "market_environment", "competitive_position"],
}

_QUALITATIVE_INSTRUCTIONS = """
You are producing a compact qualitative stock-assessment layer from supplied
evidence only.

General rules:
- Use only the provided context. Do not use outside knowledge.
- Do not invent or infer unsupported facts.
- Do not provide investment advice or Buy/Hold/Sell conclusions.
- Do not produce an overall score, assessment, or verdict.
- If evidence is mixed, prefer the middle label.
- If evidence is weak, incomplete, contradictory, or insufficient, say so in
  the evidence/drivers. Do not make a confident guess.
- Drivers explain why a label was chosen; evidence contains specific facts or
  observations grounded in the supplied context.
- Every driver must be one sentence, one idea, no more than 14 words, and no
  more than 90 characters. These are hard limits, not approximate targets.
  Before returning JSON, count each driver's words and characters and rewrite
  any driver that exceeds either limit. Avoid duplicate drivers and never
  truncate a sentence to fit.

RISK: Assess company-specific downside exposure, including supported evidence
about regulatory/legal exposure, execution, customer concentration, supplier
dependence, geographic/geopolitical exposure, business-model dependence,
balance-sheet/funding pressure, operational vulnerabilities, or technology/
product dependency. Low means relatively limited material company-specific
risks in available evidence; Medium means meaningful but manageable or mixed
risks; High means multiple significant or concentrated exposures.

MARKET ENVIRONMENT: Assess the external industry/market backdrop, primarily
from supplied market-review evidence: industry growth, demand, cyclicality,
regulation, structural tailwinds/headwinds, macro sensitivity, and competitive
intensity. Favourable means broadly supportive conditions; Neutral means mixed
or balanced conditions; Unfavourable means material external headwinds dominate.

COMPETITIVE POSITION: Assess relative strategic strength from supplied company
and peer evidence: differentiation, scale, brand, switching costs, network
effects, barriers to entry, pricing power, distribution, market position, and
competitor/substitute pressure. Strong requires multiple durable advantages
supported by evidence; Moderate means some advantages with material limitations
or mixed evidence; Weak means limited differentiation or significant
competitive disadvantage.
""".strip()

_TEXT_FIELDS = (
    "financial_performance",
    "financial_position",
    "valuation",
    "share_price_and_expectations",
    "peer_positioning",
    "recent_developments",
)

_QUALITATIVE_LABELS = {
    "risk": {"Low", "Medium", "High"},
    "market_environment": {"Unfavourable", "Neutral", "Favourable"},
    "competitive_position": {"Weak", "Moderate", "Strong"},
}

_DASHBOARD_WORD_PATTERN = re.compile(r"\b[\w]+(?:[-'][\w]+)*\b")


def _qualitative_schema(indicator_names: set[str]) -> dict[str, Any]:
    schema = {
        **QUALITATIVE_ASSESSMENT_SCHEMA,
        "properties": {
            name: QUALITATIVE_ASSESSMENT_SCHEMA["properties"][name]
            for name in _QUALITATIVE_LABELS
            if name in indicator_names
        },
        "required": [name for name in _QUALITATIVE_LABELS if name in indicator_names],
    }
    return schema


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
    if any(not is_concise_bullet(factor) for factor in factors):
        return None
    analysis["key_factors_to_watch"] = [factor.strip() for factor in factors]
    return analysis


def _validate_qualitative_assessment(value: Any) -> dict[str, dict[str, Any]]:
    """Validate each qualitative indicator independently for failure isolation."""
    if not isinstance(value, dict) or set(value) - set(_QUALITATIVE_LABELS):
        return {}

    validated: dict[str, dict[str, Any]] = {}
    for name, allowed_labels in _QUALITATIVE_LABELS.items():
        indicator = validate_qualitative_indicator(value.get(name), allowed_labels)
        if indicator is not None:
            validated[name] = indicator
    return validated


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


def _request_once(request, feature_label: str) -> str | None:
    try:
        return request()
    except Exception as exc:
        if _is_429(exc):
            print(f"{feature_label}: Gemini quota or rate limit reached.")
        else:
            print(f"{feature_label} ERROR:", repr(exc))
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
            "Do not use outside knowledge. For key_factors_to_watch, use one "
            "concise idea per bullet, roughly 10-14 words and at most 90 characters.\n\n"
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


def _request_qualitative_assessment_model(context: dict[str, Any], api_key: str) -> str:
    """Request all three qualitative indicators in one grounded Gemini call."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=(
            "Assess all three qualitative indicators from this supplied context. "
            "Return only the required JSON structure.\n\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        ),
        config=types.GenerateContentConfig(
            system_instruction=(
                _QUALITATIVE_INSTRUCTIONS
                + "\n\nReturn exactly the three qualitative indicator objects "
                "and no other fields."
            ),
            temperature=0.2,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=QUALITATIVE_ASSESSMENT_SCHEMA,
        ),
    )
    return str(getattr(response, "text", "") or "")


def _request_qualitative_recovery_model(
    context: dict[str, Any], api_key: str, indicator_names: set[str]
) -> str:
    """Request only missing qualitative indicators using the same rubric."""
    from google import genai
    from google.genai import types

    requested_names = [name for name in _QUALITATIVE_LABELS if name in indicator_names]
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=(
            "Assess only these missing qualitative indicators: "
            + ", ".join(requested_names)
            + ". Reuse only the supplied context and return only those indicator "
            "objects in the required JSON structure.\n\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        ),
        config=types.GenerateContentConfig(
            system_instruction=(
                _QUALITATIVE_INSTRUCTIONS
                + "\n\nReturn only the requested indicator objects. Do not return "
                "other indicators or additional fields."
            ),
            temperature=0.2,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=_qualitative_schema(indicator_names),
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


def generate_qualitative_assessment(
    context: dict[str, Any], eligible_indicators: set[str] | None = None
) -> dict[str, Any]:
    """Generate independently validated qualitative indicators from prior evidence."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"status": "unavailable", "indicators": {}}

    eligible = (
        set(_QUALITATIVE_LABELS)
        if eligible_indicators is None
        else set(eligible_indicators) & set(_QUALITATIVE_LABELS)
    )
    if not eligible:
        return {"status": "ok", "indicators": {}}

    cached = cache.read("feature-12b", context)
    if isinstance(cached, dict) and cached.get("status") == "ok":
        cached_indicators = _validate_qualitative_assessment(cached.get("indicators"))
        if eligible <= set(cached_indicators):
            return {"status": "ok", "indicators": cached_indicators}

    raw_response = _request_once(
        lambda: _request_qualitative_assessment_model(context, api_key),
        "FEATURE 12B",
    )
    decoded: Any = None
    try:
        if raw_response and raw_response.strip():
            decoded = json.loads(raw_response)
    except (TypeError, ValueError):
        decoded = None

    indicators = _validate_qualitative_assessment(decoded)
    missing = eligible - set(indicators)
    if missing:
        recovery_response = _request_once(
            lambda: _request_qualitative_recovery_model(
                context, api_key, missing
            ),
            "FEATURE 12B recovery",
        )
        try:
            recovery_decoded = (
                json.loads(recovery_response)
                if recovery_response and recovery_response.strip()
                else None
            )
        except (TypeError, ValueError):
            recovery_decoded = None
        recovered = _validate_qualitative_assessment(recovery_decoded)
        indicators.update(
            {
                name: value
                for name, value in recovered.items()
                if name in missing
            }
        )

    if not indicators:
        return {"status": "unavailable", "indicators": {}}
    result = {"status": "ok", "indicators": indicators}
    if eligible <= set(indicators):
        try:
            cache.write("feature-12b", context, result)
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
        if any(not is_concise_bullet(item) for item in items):
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
            "Where evidence exists, cover customer adoption and preferences, "
            "regulatory acceptance, commercialization, product-market fit, and "
            "demand-side barriers. Do not infer these without evidence. "
            "Keep each dashboard list item to one idea, roughly 10-14 words "
            "and at most 90 characters; narrative fields may be longer. "
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
                "customer adoption, preferences, product-market fit, commercialization, "
                "demand-side barriers, supply, capital needs, regulatory acceptance, or "
                "execution. Keep dashboard list items concise, at most 90 characters, "
                "and grounded in one idea. Do not put source IDs, "
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


def _bull_bear_validation_error(value: Any) -> str | None:
    if not isinstance(value, dict):
        return f"expected an object, received {type(value).__name__}"
    expected_fields = {"bull_case", "bear_case", "swing_factors"}
    missing_fields = expected_fields - set(value)
    extra_fields = set(value) - expected_fields
    if missing_fields:
        return f"missing required fields: {', '.join(sorted(missing_fields))}"
    if extra_fields:
        return f"unexpected fields: {', '.join(sorted(extra_fields))}"

    for field in ("bull_case", "bear_case"):
        items = value[field]
        if not isinstance(items, list):
            return f"{field} must be an array, received {type(items).__name__}"
        if len(items) != 3:
            return f"{field} has {len(items)} items; exactly 3 required"
        for index, item in enumerate(items):
            label = f"{field}[{index}]"
            if not isinstance(item, str):
                return f"{label} must be a string, received {type(item).__name__}"
            if not item.strip():
                return f"{label} must not be empty"
            word_count = len(_DASHBOARD_WORD_PATTERN.findall(item))
            if not 10 <= word_count <= 16:
                return f"{label} has {word_count} words; required range is 10-16"
            character_count = len(item.strip())
            if character_count > 110:
                return f"{label} has {character_count} characters; maximum is 110"
            punctuation_count = len(re.findall(r"[.!?]", item))
            if punctuation_count != 1:
                return (
                    f"{label} has {punctuation_count} sentence punctuation marks; "
                    "exactly 1 required"
                )
            if item.rstrip()[-1] not in ".!?":
                return f"{label} must end with '.', '!', or '?'"

    items = value["swing_factors"]
    if not isinstance(items, list):
        return f"swing_factors must be an array, received {type(items).__name__}"
    if len(items) != 3:
        return f"swing_factors has {len(items)} items; exactly 3 required"
    for index, item in enumerate(items):
        label = f"swing_factors[{index}]"
        if not isinstance(item, str):
            return f"{label} must be a string, received {type(item).__name__}"
        if not item.strip():
            return f"{label} must not be empty"
        word_count = len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", item))
        if not 4 <= word_count <= 10:
            return f"{label} has {word_count} words; required range is 4-10"
        character_count = len(item.strip())
        if character_count > 90:
            return f"{label} has {character_count} characters; maximum is 90"
        if re.search(r"[.!?]", item):
            return f"{label} contains sentence punctuation; none is allowed"
    return None


def _validate_bull_bear(value: Any) -> dict[str, list[str]] | None:
    if _bull_bear_validation_error(value) is not None:
        return None
    result: dict[str, list[str]] = {}
    for field in ("bull_case", "bear_case"):
        items = value.get(field)
        result[field] = [item.strip() for item in items]
    items = value["swing_factors"]
    result["swing_factors"] = [item.strip() for item in items]
    return result


def _feature11_debug_enabled() -> bool:
    return os.environ.get("DEBUG_FEATURE11") == "1"


def _feature11_debug(message: str) -> None:
    if _feature11_debug_enabled():
        print(f"FEATURE11 DEBUG: {message}")
    logger.debug("Feature 11: %s", message)


def _capture_feature11_response(
    raw_response: str | None,
    context: dict[str, Any],
    attempt: str,
) -> None:
    if not _feature11_debug_enabled():
        return
    company = context.get("company")
    ticker = str(
        company.get("ticker") if isinstance(company, dict) else "unknown"
    )
    safe_ticker = re.sub(r"[^A-Za-z0-9_.-]", "_", ticker)[:32]
    path = Path(tempfile.gettempdir()) / f"feature11-{safe_ticker}-{attempt}.txt"
    try:
        path.write_text(raw_response or "", encoding="utf-8")
    except OSError as error:
        _feature11_debug(f"{attempt} raw response capture failed ({type(error).__name__})")
        return
    text = raw_response or ""
    _feature11_debug(
        f"{attempt} raw response captured locally: {path}; "
        f"characters={len(text)}, bytes={len(text.encode('utf-8'))}, "
        f"starts_with_fence={text.lstrip().startswith('```')}, "
        f"ends_with_fence={text.rstrip().endswith('```')}"
    )


def _request_bull_bear_content(prompt: str, api_key: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "Return only one JSON object matching the supplied schema. "
                "Do not include markdown, fences, or prose."
            ),
            temperature=0.2,
            max_output_tokens=2048,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MINIMAL
            ),
            response_mime_type="application/json",
            response_schema=BULL_BEAR_SCHEMA,
        ),
    )
    if _feature11_debug_enabled():
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None
        usage = getattr(response, "usage_metadata", None)
        feedback = getattr(response, "prompt_feedback", None)
        _feature11_debug(
            "provider response metadata: "
            f"candidate_count={len(candidates)}, "
            f"finish_reason={getattr(candidate, 'finish_reason', None)}, "
            f"prompt_tokens={getattr(usage, 'prompt_token_count', None)}, "
            f"output_tokens={getattr(usage, 'candidates_token_count', None)}, "
            f"thinking_tokens={getattr(usage, 'thoughts_token_count', None)}, "
            f"cached_content_tokens={getattr(usage, 'cached_content_token_count', None)}, "
            f"total_tokens={getattr(usage, 'total_token_count', None)}, "
            f"model={MODEL_NAME}, max_output_tokens=2048, "
            "thinking_level=MINIMAL, thinking_budget=None, "
            f"prompt_block_reason={getattr(feedback, 'block_reason', None)}"
        )
    return str(getattr(response, "text", "") or "")


def _request_bull_bear_model(context: dict[str, Any], api_key: str) -> str:
    """Request the primary Feature 11 response with its existing methodology."""
    prompt = (
        "Create exactly three conditional bull-case arguments, three conditional "
        "bear-case arguments, and three concise swing factors from ONLY this evidence. "
        "Return exactly the keys bull_case, bear_case, and swing_factors, with no "
        "additional keys. Each case array must contain exactly 3 non-empty strings. "
        "Count words as dashboard tokens: letters/digits/underscores grouped together, "
        "with internal hyphens or apostrophes joining one token. Each bull_case and "
        "bear_case string must be 10-16 such words and no more than 110 characters, "
        "counting every letter, space, and punctuation mark. Count the characters "
        "before returning each bullet; target 90-100 characters for margin and rewrite "
        "any bullet over 100 characters. Each case bullet must be one sentence, ending "
        "in exactly one period, exclamation mark, or question mark. Each "
        "swing_factors string must be 4-10 words using the same word definition, at "
        "most 90 characters, and contain no period, exclamation mark, or question mark. "
        "Use one clear evidence -> business mechanism -> potential implication. "
        "Do not use analyst forecasts or metrics as the mechanism itself; use the "
        "underlying demand, pricing, competition, capacity, execution, or financial "
        "driver, with forecasts only as supporting evidence. Avoid subordinate clauses, "
        "deterministic claims, excessive numbers, recommendations, and target prices. "
        "Use cautious wording such as could, may, or increases exposure to. Do not "
        "provide outside facts.\n\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )
    return _request_bull_bear_content(prompt, api_key)


def _request_bull_bear_repair_model(
    context: dict[str, Any],
    api_key: str,
    invalid_response: str,
) -> str:
    """Repair one invalid Feature 11 response using only the original evidence."""
    prompt = (
        "The previous output failed the required schema. Repair its formatting and "
        "constraints without changing the analytical methodology or adding evidence. "
        "Use ONLY the supplied context; do no web research and add no outside facts. "
        "Return ONLY one valid JSON object with exactly these keys and no others: "
        '{"bull_case":[three strings],"bear_case":[three strings],'
        '"swing_factors":[three strings]}. Each case array must contain exactly 3 '
        "non-empty strings. Count words as dashboard tokens: letters/digits/underscores "
        "grouped together, with internal hyphens or apostrophes joining one token. "
        "Each case string must be 10-16 such words and no more than 110 characters, "
        "counting every letter, space, and punctuation mark. Count each bullet's "
        "characters before returning; target 90-100 characters for margin and rewrite "
        "any bullet over 100 characters. Each case bullet must be one sentence, ending "
        "in exactly one period, exclamation mark, or question mark. Each "
        "swing factor must be 4-10 such words, at most 90 "
        "characters, and contain no period, exclamation mark, or question mark. "
        "No markdown, code fences, or prose.\n\n"
        "Evidence context:\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        + "\n\nPrevious invalid output:\n"
        + invalid_response[:4_000]
    )
    return _request_bull_bear_content(prompt, api_key)


def _parse_bull_bear_response(
    raw_response: str | None,
    attempt: str,
) -> dict[str, list[str]] | None:
    if not raw_response or not raw_response.strip():
        _feature11_debug(f"{attempt}: response empty")
        return None
    _feature11_debug(f"{attempt}: response non-empty ({len(raw_response)} characters)")
    try:
        decoded = json.loads(raw_response)
    except (TypeError, ValueError) as error:
        if isinstance(error, json.JSONDecodeError):
            reason = (
                f"{error.msg} (line {error.lineno}, column {error.colno}, "
                f"character {error.pos})"
            )
        else:
            reason = f"{type(error).__name__}: {error}"
        _feature11_debug(f"{attempt}: JSON parsing failed: {reason}")
        return None
    _feature11_debug(f"{attempt}: JSON parsing succeeded")
    validation_error = _bull_bear_validation_error(decoded)
    if validation_error is not None:
        _feature11_debug(f"{attempt}: schema validation failed: {validation_error}")
        return None
    _feature11_debug(f"{attempt}: schema validation succeeded")
    validated = _validate_bull_bear(decoded)
    return validated


def generate_bull_bear(context: dict[str, Any]) -> dict[str, Any]:
    """Generate validated Feature 11 scenario analysis or a safe unavailable result."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        _feature11_debug("API key unavailable; no request made")
        return {"status": "unavailable", "message": "Bull / Bear analysis temporarily unavailable.", "analysis": None}

    _feature11_debug("cache checked")
    cached = cache.read("feature-11", context)
    if isinstance(cached, dict) and cached.get("status") == "ok":
        cached_analysis = _validate_bull_bear(cached.get("analysis"))
        if cached_analysis is not None:
            _feature11_debug("cache hit")
            return {"status": "ok", "message": None, "analysis": cached_analysis}
    _feature11_debug("cache miss")

    try:
        raw_response = _request_bull_bear_model(context, api_key)
    except Exception:
        _feature11_debug("primary request raised provider exception")
        logger.debug("Feature 11 primary Gemini request failed", exc_info=True)
        return {"status": "unavailable", "message": "Bull / Bear analysis temporarily unavailable.", "analysis": None}

    _feature11_debug("primary request succeeded")
    _capture_feature11_response(raw_response, context, "primary")
    analysis = _parse_bull_bear_response(raw_response, "primary")
    if analysis is None:
        _feature11_debug("repair triggered")
        try:
            repair_response = _request_bull_bear_repair_model(
                context,
                api_key,
                raw_response or "",
            )
        except Exception:
            _feature11_debug("repair request raised provider exception")
            logger.debug("Feature 11 repair Gemini request failed", exc_info=True)
            return {"status": "unavailable", "message": "Bull / Bear analysis temporarily unavailable.", "analysis": None}
        _feature11_debug("repair request succeeded")
        _capture_feature11_response(repair_response, context, "repair")
        analysis = _parse_bull_bear_response(repair_response, "repair")
        if analysis is None:
            _feature11_debug("repair validation failed; returning unavailable")
            logger.debug("Feature 11 repair failed; returning unavailable result")
            return {"status": "unavailable", "message": "Bull / Bear analysis temporarily unavailable.", "analysis": None}
        _feature11_debug("repair validation succeeded")
        logger.debug("Feature 11 repair succeeded")

    result = {"status": "ok", "message": None, "analysis": analysis}
    _feature11_debug("final status: ok")
    try:
        cache.write("feature-11", context, result)
    except (OSError, TypeError, ValueError):
        pass
    return result