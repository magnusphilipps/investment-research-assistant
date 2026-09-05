import json
import os
import unittest
from unittest.mock import patch

import pandas as pd

from investment_research import display
from investment_research.analysis import build_analysis_context
from investment_research.gemini_provider import generate_analysis


def _valid_model_response():
    return json.dumps({
        "financial_performance": "Revenue growth is positive, but margins remain under pressure.",
        "financial_position": "Cash provides liquidity while debt remains a factor to monitor.",
        "valuation": "The available multiples should be interpreted alongside the earnings trend.",
        "share_price_and_expectations": "The stock has outperformed the benchmark while analyst expectations remain mixed.",
        "peer_positioning": "The company is broadly competitive on the supplied peer metrics.",
        "recent_developments": "Recent company-specific developments should be monitored alongside operating results.",
        "key_factors_to_watch": [
            "Whether revenue growth translates into better operating margins.",
            "Changes in free cash flow and liquidity.",
            "Whether valuation remains supported by the supplied expectations.",
        ],
    })


class AnalysisContextTests(unittest.TestCase):
    def test_context_uses_existing_structured_results_and_flattens_peer_dataframe(self):
        context = build_analysis_context(
            "aapl",
            {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "description": "A company description.",
                "price": 200.0,
                "market_cap": 1_000_000,
            },
            {
                "currency_code": "USD",
                "income": {
                    "years": ["2025", "2024"],
                    "revenue": [100.0, 80.0],
                    "revenue_growth": [25.0],
                    "gross_margin": [45.0, 43.0],
                    "op_margin": [20.0, 18.0],
                    "net_income": [15.0, 12.0],
                    "eps_diluted": [1.5, 1.2],
                    "acceleration": "Accelerating",
                },
                "balance": {
                    "cash": 50.0,
                    "total_debt": 20.0,
                    "equity": 100.0,
                    "current_ratio": 1.8,
                    "de_ratio": 0.2,
                },
                "cashflow": {"free_cash_flow": 10.0},
            },
            {"valuation": {"trailing_pe": 22.0, "forward_pe": 19.0}},
            {
                "returns": {"1 Year": 0.15},
                "range": {"high": 210.0, "low": 140.0},
                "benchmark": {"1 Year": {"difference": 0.03}},
                "latest_date": "2026-09-01",
                "retrieved_at": "not needed",
            },
            {"price_targets": {"average_target": 220.0}},
            {
                "available": True,
                "tickers": ["AAPL", "MSFT"],
                "df": pd.DataFrame(
                    {"AAPL": [25.0], "MSFT": [20.0]},
                    index=["Revenue Growth"],
                ),
                "summary": ["AAPL has higher revenue growth."],
            },
            {
                "status": "ok",
                "articles": [{
                    "title": "Apple update",
                    "source": "Example News",
                    "published_at": "2026-09-01T10:00:00Z",
                    "description": "A company-specific update.",
                    "url": "https://example.com/apple",
                }],
            },
        )

        self.assertEqual(context["company"]["ticker"], "AAPL")
        self.assertEqual(context["financial_performance"]["revenue"], [100.0, 80.0])
        self.assertEqual(context["valuation"]["trailing_pe"], 22.0)
        self.assertEqual(
            context["peer_positioning"]["metrics"]["Revenue Growth"]["AAPL"],
            25.0,
        )
        self.assertEqual(context["recent_news"]["articles"][0]["title"], "Apple update")
        self.assertNotIn("retrieved_at", json.dumps(context))
        self.assertNotIn('"N/A"', json.dumps(context))

    def test_missing_fields_remain_null_or_empty(self):
        context = build_analysis_context(
            "AAPL", {}, {"income": {"error": "unavailable"}}, {}, None, None, None, None
        )

        self.assertIsNone(context["company"]["name"])
        self.assertEqual(context["financial_performance"]["revenue"], [])
        self.assertEqual(context["recent_news"]["articles"], [])
        self.assertNotIn('"N/A"', json.dumps(context))


class GeminiProviderTests(unittest.TestCase):
    def test_missing_key_does_not_call_provider(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "investment_research.gemini_provider._request_model"
        ) as request:
            result = generate_analysis({})

        self.assertEqual(result["status"], "unavailable")
        request.assert_not_called()

    def test_successful_structured_response_is_validated(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider._request_model",
            return_value=_valid_model_response(),
        ) as request:
            result = generate_analysis({"company": {"ticker": "AAPL"}})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["analysis"]["key_factors_to_watch"]), 3)
        request.assert_called_once_with({"company": {"ticker": "AAPL"}}, "test-key")
        self.assertNotIn("test-key", json.dumps(result))

    def test_provider_error_malformed_response_and_empty_response_are_safe(self):
        for response in (RuntimeError("provider failed"), "not json", ""):
            with self.subTest(response=response), patch.dict(
                os.environ, {"GOOGLE_API_KEY": "test-key"}
            ), patch(
                "investment_research.gemini_provider._request_model",
                side_effect=response if isinstance(response, Exception) else None,
                return_value=None if isinstance(response, Exception) else response,
            ):
                result = generate_analysis({})
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["analysis"])

    def test_invalid_structured_response_is_rejected(self):
        invalid = json.dumps({"financial_performance": "Only one field."})
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider._request_model",
            return_value=invalid,
        ):
            result = generate_analysis({})

        self.assertEqual(result["status"], "unavailable")


class AnalysisDisplayTests(unittest.TestCase):
    def test_display_formats_success_without_printing_raw_json(self):
        result = {
            "status": "ok",
            "analysis": {
                "financial_performance": "Growth remains strong.",
                "financial_position": "Liquidity is adequate.",
                "valuation": "Multiples require context.",
                "share_price_and_expectations": "Performance is positive.",
                "peer_positioning": "Peer data is mixed.",
                "recent_developments": "No major development was supplied.",
                "key_factors_to_watch": ["Growth", "Cash flow", "Valuation"],
            },
        }
        with patch("builtins.print") as printer:
            display.print_ai_analysis(result)

        output = " ".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("AI ANALYSIS", output)
        self.assertIn("Financial Performance", output)
        self.assertIn("Key Factors to Watch", output)
        self.assertNotIn("'financial_performance'", output)

    def test_display_formats_unavailable_state(self):
        with patch("builtins.print") as printer:
            display.print_ai_analysis({
                "status": "unavailable",
                "message": "provider details must stay hidden",
                "analysis": None,
            })

        output = " ".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("AI analysis temporarily unavailable.", output)
        self.assertNotIn("provider details", output)


if __name__ == "__main__":
    unittest.main()