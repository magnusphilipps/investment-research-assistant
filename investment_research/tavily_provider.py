"""Tavily-specific external research retrieval."""

from __future__ import annotations

import os
from typing import Any

import requests


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
REQUEST_TIMEOUT_SECONDS = 15
MAX_RESULTS_PER_QUERY = 5


def search(query: str, *, max_results: int = MAX_RESULTS_PER_QUERY) -> list[dict[str, Any]]:
    """Retrieve search results while keeping Tavily details out of other layers."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return []

    response = requests.post(
        TAVILY_SEARCH_URL,
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
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
