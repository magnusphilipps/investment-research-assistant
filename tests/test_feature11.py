import json
import os
import inspect
import unittest
from unittest.mock import patch

from investment_research import analysis, display
from investment_research.gemini_provider import generate_analysis, generate_bull_bear


def _valid_analysis_response():
    return json.dumps({
        "financial_performance": "Revenue growth remains positive.",
        "financial_position": "Liquidity remains available.",
        "valuation": "The supplied multiples require context.",
        "share_price_and_expectations": "Performance and expectations are mixed.",
        "peer_positioning": "Peer evidence is incomplete.",
        "recent_developments": "Recent developments require monitoring.",
        "key_factors_to_watch": ["Growth", "Margins", "Cash flow"],
    })


def _valid_bull_bear_response():
    return json.dumps({
        "bull_case": [
            "Strong enterprise demand could support rapid cloud revenue scaling and improved operating leverage.",
            "Higher infrastructure utilization could support margin expansion and stronger operating cash generation.",
            "Improved execution could strengthen customer retention and support more predictable capacity growth.",
        ],
        "bear_case": [
            "Power-grid delays could constrain data-center expansion and slow available capacity growth.",
            "Falling rental prices could pressure revenue growth and reduce cloud operating margins.",
            "Heavy capital spending could prolong negative free cash flow and increase liquidity pressure.",
        ],
        "swing_factors": [
            "Speed of power approvals",
            "Enterprise adoption of GPU clouds",
            "Direction of GPU rental pricing",
        ],
    })


class Feature11Tests(unittest.TestCase):
    def test_bull_bear_requires_exactly_three_nonempty_items(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider._request_bull_bear_model",
            return_value=json.dumps({
                "bull_case": ["one", "two"],
                "bear_case": ["one", "two", "three"],
                "swing_factors": ["one", "two", "three"],
            }),
        ), patch("investment_research.gemini_provider.cache.read", return_value=None):
            result = generate_bull_bear({})
        self.assertEqual(result["status"], "unavailable")

    def test_bull_and_bear_word_limits_are_enforced(self):
        valid = json.loads(_valid_bull_bear_response())
        for field in ("bull_case", "bear_case"):
            for count in (9, 17):
                invalid = {**valid, field: [(" ".join(["word"] * count) + ".")] + valid[field][1:]}
                with self.subTest(field=field, count=count), patch.dict(
                    os.environ, {"GOOGLE_API_KEY": "test-key"}
                ), patch(
                    "investment_research.gemini_provider._request_bull_bear_model",
                    return_value=json.dumps(invalid),
                ):
                    self.assertEqual(generate_bull_bear({})["status"], "unavailable")

    def test_swing_factor_word_limits_are_enforced(self):
        valid = json.loads(_valid_bull_bear_response())
        for count in (3, 11):
            invalid = {**valid, "swing_factors": [" ".join(["word"] * count)] + valid["swing_factors"][1:]}
            with self.subTest(count=count), patch.dict(
                os.environ, {"GOOGLE_API_KEY": "test-key"}
            ), patch(
                "investment_research.gemini_provider._request_bull_bear_model",
                return_value=json.dumps(invalid),
            ):
                self.assertEqual(generate_bull_bear({})["status"], "unavailable")

    def test_prompt_discourages_forecast_tautologies(self):
        from investment_research import gemini_provider

        prompt_source = inspect.getsource(gemini_provider._request_bull_bear_model)
        self.assertIn("underlying demand", prompt_source)
        self.assertIn("forecasts only as supporting evidence", prompt_source)

    def test_valid_bull_bear_result_has_three_sections(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider._request_bull_bear_model",
            return_value=_valid_bull_bear_response(),
        ), patch("investment_research.gemini_provider.cache.read", return_value=None):
            result = generate_bull_bear({})
        self.assertEqual(result["status"], "ok")
        self.assertEqual([len(result["analysis"][key]) for key in (
            "bull_case", "bear_case", "swing_factors"
        )], [3, 3, 3])

    def test_feature_nine_cache_hit_avoids_provider_call(self):
        cached = {"status": "ok", "message": None, "analysis": {
            "financial_performance": "Cached.",
            "financial_position": "Cached.",
            "valuation": "Cached.",
            "share_price_and_expectations": "Cached.",
            "peer_positioning": "Cached.",
            "recent_developments": "Cached.",
            "key_factors_to_watch": ["One", "Two", "Three"],
        }}
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=cached
        ), patch("investment_research.gemini_provider._request_model") as request:
            result = generate_analysis({"company": {"ticker": "AAPL"}})
        self.assertEqual(result, cached)
        request.assert_not_called()

    def test_invalid_result_is_not_cached(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_model", return_value="{}"
        ), patch("investment_research.gemini_provider.cache.write") as write:
            result = generate_analysis({})
        self.assertEqual(result["status"], "unavailable")
        write.assert_not_called()

    def test_cache_write_failure_does_not_discard_valid_result(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_model",
            return_value=_valid_analysis_response(),
        ), patch(
            "investment_research.gemini_provider.cache.write",
            side_effect=OSError("read-only cache"),
        ):
            result = generate_analysis({"company": {"ticker": "MSFT"}})
        self.assertEqual(result["status"], "ok")

    def test_503_retries_but_429_fails_once(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_model",
            side_effect=[RuntimeError("503 high demand"), _valid_analysis_response()],
        ) as request, patch("investment_research.gemini_provider.time.sleep") as sleep:
            result = generate_analysis({})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(2)

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider._request_model",
            side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"),
        ) as request, patch("investment_research.gemini_provider.time.sleep") as sleep, patch(
            "investment_research.gemini_provider.cache.read",
            return_value=None,
        ):
            result = generate_analysis({})
        self.assertEqual(result["status"], "unavailable")
        request.assert_called_once()
        sleep.assert_not_called()

    def test_503_stops_after_three_attempts(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_model",
            side_effect=RuntimeError("503 high demand"),
        ) as request, patch("investment_research.gemini_provider.time.sleep"):
            result = generate_analysis({"company": {"ticker": "TSLA"}})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(request.call_count, 3)

    def test_feature_eleven_context_keeps_external_review_separate(self):
        context = analysis.build_bull_bear_context(
            {"company": {"ticker": "AAPL"}},
            {"status": "ok", "review": {"market_outlook": "Demand may improve."}, "sources": []},
        )
        self.assertEqual(context["external_market_evidence"]["review"]["market_outlook"], "Demand may improve.")
        self.assertNotIn("market_outlook", context["company"])

    def test_display_has_three_named_sections(self):
        result = {"status": "ok", "analysis": {
            "bull_case": ["Bull one", "Bull two", "Bull three"],
            "bear_case": ["Bear one", "Bear two", "Bear three"],
            "swing_factors": ["Swing one", "Swing two", "Swing three"],
        }}
        with patch("builtins.print") as printer:
            display.print_bull_bear_analysis(result)
        output = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("BULL CASE", output)
        self.assertIn("BEAR CASE", output)
        self.assertIn("KEY SWING FACTORS", output)


if __name__ == "__main__":
    unittest.main()
