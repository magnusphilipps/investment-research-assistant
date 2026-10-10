import json
import os
import inspect
import unittest
from unittest.mock import patch

from investment_research import analysis, display
from investment_research.gemini_provider import (
    _request_bull_bear_content,
    _validate_bull_bear,
    generate_analysis,
    generate_bull_bear,
)


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
            "Enterprise demand could support cloud growth and stronger operating leverage.",
            "Higher infrastructure use could improve margins and strengthen operating cash flow.",
            "Better execution could improve retention and support steadier capacity growth.",
        ],
        "bear_case": [
            "Power delays could slow data-center expansion and constrain available capacity.",
            "Lower rental prices could pressure revenue growth and weaken operating margins.",
            "Heavy spending could prolong negative free cash flow and increase funding pressure.",
        ],
        "swing_factors": [
            "Speed of power approvals",
            "Enterprise adoption of GPU clouds",
            "Direction of GPU rental pricing",
        ],
    })


class Feature11Tests(unittest.TestCase):
    def setUp(self):
        cache_read = patch(
            "investment_research.gemini_provider.cache.read",
            return_value=None,
        )
        cache_write = patch("investment_research.gemini_provider.cache.write")
        cache_read.start()
        cache_write.start()
        self.addCleanup(cache_read.stop)
        self.addCleanup(cache_write.stop)

    def test_bull_bear_requires_exactly_three_nonempty_items(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider._request_bull_bear_model",
            return_value=json.dumps({
                "bull_case": ["one", "two"],
                "bear_case": ["one", "two", "three"],
                "swing_factors": ["one", "two", "three"],
            }),
        ), patch(
            "investment_research.gemini_provider._request_bull_bear_repair_model",
            return_value="{}",
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
                ), patch(
                    "investment_research.gemini_provider._request_bull_bear_repair_model",
                    return_value="{}",
                ):
                    self.assertEqual(generate_bull_bear({})["status"], "unavailable")

    def test_bull_bear_boundaries_accept_16_words_and_110_characters(self):
        valid = json.loads(_valid_bull_bear_response())
        sixteen_words = " ".join(["word"] * 15 + ["impact."])
        exactly_110_chars = " ".join(["a" * 10] * 9 + ["b" * 10 + "."])
        self.assertEqual(len(exactly_110_chars), 110)

        for field in ("bull_case", "bear_case"):
            with self.subTest(field=field, boundary="16 words"):
                result = _validate_bull_bear({
                    **valid,
                    field: [sixteen_words, *valid[field][1:]],
                })
                self.assertIsNotNone(result)
            with self.subTest(field=field, boundary="17 words"):
                seventeen_words = " ".join(["word"] * 16 + ["impact."])
                result = _validate_bull_bear({
                    **valid,
                    field: [seventeen_words, *valid[field][1:]],
                })
                self.assertIsNone(result)
            with self.subTest(field=field, boundary="110 characters"):
                result = _validate_bull_bear({
                    **valid,
                    field: [exactly_110_chars, *valid[field][1:]],
                })
                self.assertIsNotNone(result)
            with self.subTest(field=field, boundary="111 characters"):
                one_over = " ".join(["a" * 10] * 9 + ["b" * 11 + "."])
                self.assertEqual(len(one_over), 111)
                result = _validate_bull_bear({
                    **valid,
                    field: [one_over, *valid[field][1:]],
                })
                self.assertIsNone(result)

    def test_swing_factor_word_limits_are_enforced(self):
        valid = json.loads(_valid_bull_bear_response())
        for count in (3, 11):
            invalid = {**valid, "swing_factors": [" ".join(["word"] * count)] + valid["swing_factors"][1:]}
            with self.subTest(count=count), patch.dict(
                os.environ, {"GOOGLE_API_KEY": "test-key"}
            ), patch(
                "investment_research.gemini_provider._request_bull_bear_model",
                return_value=json.dumps(invalid),
            ), patch(
                "investment_research.gemini_provider._request_bull_bear_repair_model",
                return_value="{}",
            ):
                self.assertEqual(generate_bull_bear({})["status"], "unavailable")

    def test_prompt_discourages_forecast_tautologies(self):
        from investment_research import gemini_provider

        prompt_source = inspect.getsource(gemini_provider._request_bull_bear_model)
        self.assertIn("underlying demand", prompt_source)
        self.assertIn("forecasts only as supporting evidence", prompt_source)

    def test_bull_bear_request_uses_json_schema_and_2048_token_budget(self):
        from investment_research import gemini_provider

        with patch("google.genai.Client") as client_class:
            client_class.return_value.models.generate_content.return_value.text = "{}"

            response = _request_bull_bear_content("prompt", "test-key")

        self.assertEqual(response, "{}")
        config = client_class.return_value.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.max_output_tokens, 2048)
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertIsNotNone(config.response_schema)
        self.assertEqual(
            config.thinking_config.thinking_level.value,
            "MINIMAL",
        )
        self.assertIsNone(config.thinking_config.thinking_budget)
        self.assertEqual(
            gemini_provider.BULL_BEAR_SCHEMA["properties"]["bull_case"]["items"]["maxLength"],
            110,
        )
        self.assertEqual(
            gemini_provider.BULL_BEAR_SCHEMA["properties"]["bear_case"]["items"]["maxLength"],
            110,
        )

    def test_primary_and_repair_prompts_state_case_bullet_limits(self):
        from investment_research import gemini_provider

        with patch(
            "investment_research.gemini_provider._request_bull_bear_content",
            return_value="{}",
        ) as request:
            gemini_provider._request_bull_bear_model({"company": {}}, "test-key")
            primary_prompt = request.call_args.args[0]
            gemini_provider._request_bull_bear_repair_model(
                {"company": {}},
                "test-key",
                "{}",
            )
            repair_prompt = request.call_args.args[0]

        for prompt in (primary_prompt, repair_prompt):
            self.assertIn("10-16", prompt)
            self.assertIn("110 characters", prompt)
            self.assertIn("target 90-100 characters", prompt)
            self.assertIn("4-10", prompt)
            self.assertIn("at most 90 characters", prompt)

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

    def _run_bull_bear_responses(self, primary, repair=""):
        context = {"company": {"ticker": "TEST"}}
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read",
            return_value=None,
        ), patch(
            "investment_research.gemini_provider.cache.write",
        ) as cache_write, patch(
            "investment_research.gemini_provider._request_bull_bear_model",
            return_value=primary,
        ) as primary_request, patch(
            "investment_research.gemini_provider._request_bull_bear_repair_model",
            return_value=repair,
        ) as repair_request:
            result = generate_bull_bear(context)
        return result, context, primary_request, repair_request, cache_write

    def test_primary_valid_response_uses_one_call_and_preserves_output_contract(self):
        result, _, primary, repair, cache_write = self._run_bull_bear_responses(
            _valid_bull_bear_response()
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(set(result), {"status", "message", "analysis"})
        self.assertEqual(
            set(result["analysis"]),
            {"bull_case", "bear_case", "swing_factors"},
        )
        self.assertEqual([len(result["analysis"][key]) for key in (
            "bull_case", "bear_case", "swing_factors"
        )], [3, 3, 3])
        primary.assert_called_once()
        repair.assert_not_called()
        cache_write.assert_called_once_with("feature-11", {"company": {"ticker": "TEST"}}, result)

    def test_malformed_primary_is_repaired_once_and_repaired_result_is_cached(self):
        result, context, primary, repair, cache_write = self._run_bull_bear_responses(
            "{not-json",
            _valid_bull_bear_response(),
        )

        self.assertEqual(result["status"], "ok")
        primary.assert_called_once_with(context, "test-key")
        repair.assert_called_once_with(context, "test-key", "{not-json")
        cache_write.assert_called_once_with("feature-11", context, result)

    def test_schema_invalid_primary_is_repaired_once(self):
        invalid = json.dumps({
            **json.loads(_valid_bull_bear_response()),
            "bull_case": ["wrong type"],
        })
        result, context, primary, repair, cache_write = self._run_bull_bear_responses(
            invalid,
            _valid_bull_bear_response(),
        )

        self.assertEqual(result["status"], "ok")
        primary.assert_called_once()
        repair.assert_called_once_with(context, "test-key", invalid)
        cache_write.assert_called_once()

    def test_malformed_primary_and_repair_return_unavailable_without_caching(self):
        result, _, primary, repair, cache_write = self._run_bull_bear_responses(
            "{invalid",
            "```json\n{invalid again}\n```",
        )

        self.assertEqual(result, {
            "status": "unavailable",
            "message": "Bull / Bear analysis temporarily unavailable.",
            "analysis": None,
        })
        primary.assert_called_once()
        repair.assert_called_once()
        self.assertLessEqual(primary.call_count + repair.call_count, 2)
        cache_write.assert_not_called()

    def test_valid_feature_11_cache_hit_uses_existing_context_key_without_gemini(self):
        context = {"company": {"ticker": "TEST"}}
        cached = {
            "status": "ok",
            "message": None,
            "analysis": json.loads(_valid_bull_bear_response()),
        }
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read",
            return_value=cached,
        ) as cache_read, patch(
            "investment_research.gemini_provider._request_bull_bear_model",
        ) as primary, patch(
            "investment_research.gemini_provider._request_bull_bear_repair_model",
        ) as repair:
            result = generate_bull_bear(context)

        self.assertEqual(result["status"], "ok")
        cache_read.assert_called_once_with("feature-11", context)
        primary.assert_not_called()
        repair.assert_not_called()

    def test_provider_failure_does_not_start_repair(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read",
            return_value=None,
        ), patch(
            "investment_research.gemini_provider.cache.write",
        ) as cache_write, patch(
            "investment_research.gemini_provider._request_bull_bear_model",
            side_effect=RuntimeError("provider unavailable"),
        ) as primary, patch(
            "investment_research.gemini_provider._request_bull_bear_repair_model",
        ) as repair:
            result = generate_bull_bear({"company": {"ticker": "TEST"}})

        self.assertEqual(result["status"], "unavailable")
        primary.assert_called_once()
        repair.assert_not_called()
        cache_write.assert_not_called()

    def test_feature_11_makes_no_external_research_or_company_provider_calls(self):
        from investment_research import fetcher, news, tavily_provider

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read",
            return_value=None,
        ), patch(
            "investment_research.gemini_provider.cache.write",
        ), patch(
            "investment_research.gemini_provider._request_bull_bear_model",
            return_value=_valid_bull_bear_response(),
        ), patch.object(tavily_provider, "search") as tavily_search, patch.object(
            fetcher.yf, "Ticker"
        ) as yahoo_ticker, patch.object(news.requests, "get") as marketaux_get:
            result = generate_bull_bear({"company": {"ticker": "TEST"}})

        self.assertEqual(result["status"], "ok")
        tavily_search.assert_not_called()
        yahoo_ticker.assert_not_called()
        marketaux_get.assert_not_called()

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
