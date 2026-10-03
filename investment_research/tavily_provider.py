"""Tavily-specific external research retrieval."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
REQUEST_TIMEOUT_SECONDS = 15
MAX_RESULTS_PER_QUERY = 7
LOGGER = logging.getLogger(__name__)


def search(
    query: str, *, max_results: int = MAX_RESULTS_PER_QUERY, search_depth: str = "basic"
) -> list[dict[str, Any]]:
    """Retrieve search results while keeping Tavily details out of other layers."""
    if search_depth not in {"basic", "advanced"}:
        raise ValueError("search_depth must be 'basic' or 'advanced'")
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return []

    LOGGER.debug(
        "Tavily search request; depth=%s results=%d",
        search_depth,
        max_results,
    )
    response = requests.post(
        TAVILY_SEARCH_URL,
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else None
    return results if isinstance(results, list) else []
