import json
import os
import unittest
from unittest.mock import patch

from investment_research import assessment
from investment_research.gemini_provider import generate_qualitative_assessment


def _valid_indicators():
    return {
        "risk": {
            "label": "Medium",
            "drivers": ["Debt remains manageable.", "Execution exposure is mixed."],
            "evidence": ["Debt-to-equity is 0.8.", "Feature 9 lists execution as a factor to watch."],
        },
        "market_environment": {
            "label": "Favourable",
            "drivers": ["Industry demand is supportive.", "Tailwinds outweigh identified headwinds."],
            "evidence": ["Feature 10 describes positive demand.", "The review identifies structural growth drivers."],
        },
        "competitive_position": {
            "label": "Strong",
            "drivers": ["Peer positioning indicates an advantage.", "The supplied analysis describes differentiated execution."],
            "evidence": ["Feature 9 reports favourable peer positioning.", "Peer notes include operating-margin comparisons."],
        },
    }


def _assessment_context():
    return {
        "ticker": "EXM",
        "company": {
            "name": "Example Corp",
            "sector": "Technology",
            "industry": "Software",
            "description": "Provides business software.",
            "country": "United States",
        },
        "financials": {
            "income": {
                "revenue": [1000.0],
                "revenue_growth": [12.0],
                "op_margin": [18.0],
                "net_income": [100.0],
            },
            "cashflow": {"free_cash_flow": [140.0], "operating_cf": [180.0]},
        },
        "ratios": {
            "profitability": {"op_margin": 18.0},
            "strength": {"de_ratio": 0.8, "current_ratio": 1.6},
            "valuation": {"trailing_pe": 18.0, "forward_pe": 16.0, "ev_ebitda": 12.0},
        },
        "performance": {"annualized_volatility": 0.2, "beta": 1.0, "max_drawdown": 0.15},
        "analyst_expectations": {
            "revenue_estimates": {"next_year": {"growth": 10.0}},
            "recommendations": {"Buy": 5, "Hold": 2, "Sell": 1},
            "price_targets": {"implied_upside": 0.1},
        },
        "peer_comparison": {
            "tickers": ["EXM", "PEER1", "PEER2"],
            "summary": ["Example Corp operating margin is above the peer median."],
        },
        "company_analysis": {
            "financial_performance": "Revenue is growing and operating margin is positive.",
            "financial_position": "Cash generation is positive with moderate debt.",
            "peer_positioning": "Operating margin compares favourably with supplied peers.",
            "recent_developments": "No material development is supplied.",
            "key_factors_to_watch": ["Execution against growth plans", "Customer retention"],
        },
        "market_review": {
            "status": "ok",
            "review": {
                "industry_overview": "Software demand remains active.",
                "market_outlook": "Demand growth is expected to remain supportive.",
                "growth_drivers": ["Cloud adoption supports demand."],
                "industry_risks": ["Competition may pressure pricing."],
                "competitive_dynamics": ["Competition remains active."],
                "company_implications": [
                    "Demand may change.", "Execution matters.", "Competition matters.",
                ],
            },
            "sources": [{"id": "S1", "title": "Industry overview", "content": "Supplied market evidence."}],
        },
    }


class TestFeature12B(unittest.TestCase):
    def test_raw_model_response_with_three_compliant_indicators_survives_both_validation_stages(self):
        raw_response = json.dumps(_valid_indicators())
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=raw_response,
        ) as model_request, patch(
            "investment_research.gemini_provider.cache.write"
        ):
            result = assessment.build_stock_assessment(_assessment_context())

        model_request.assert_called_once()
        self.assertEqual(
            {
                key: result["indicators"][key]["label"]
                for key in ("risk", "market_environment", "competitive_position")
            },
            {
                "risk": "Medium",
                "market_environment": "Favourable",
                "competitive_position": "Strong",
            },
        )

    def test_all_valid_indicators_do_not_trigger_recovery(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=json.dumps(_valid_indicators()),
        ) as primary, patch(
            "investment_research.gemini_provider._request_qualitative_recovery_model"
        ) as recovery, patch("investment_research.gemini_provider.cache.write"):
            result = generate_qualitative_assessment(_assessment_context())

        primary.assert_called_once()
        recovery.assert_not_called()
        self.assertEqual(set(result["indicators"]), set(_valid_indicators()))

    def test_one_rejected_eligible_indicator_is_recovered_and_merged(self):
        primary_indicators = _valid_indicators()
        primary_indicators["competitive_position"]["drivers"][0] = (
            "A too long driver includes claims, details, and clauses beyond the required concise length."
        )
        recovered_indicator = {
            "competitive_position": _valid_indicators()["competitive_position"],
        }
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=json.dumps(primary_indicators),
        ) as primary, patch(
            "investment_research.gemini_provider._request_qualitative_recovery_model",
            return_value=json.dumps(recovered_indicator),
        ) as recovery, patch("investment_research.gemini_provider.cache.write") as cache_write:
            result = generate_qualitative_assessment(_assessment_context())

        primary.assert_called_once_with(_assessment_context(), "test-key")
        recovery.assert_called_once_with(
            _assessment_context(), "test-key", {"competitive_position"}
        )
        self.assertEqual(set(result["indicators"]), set(_valid_indicators()))
        self.assertEqual(
            result["indicators"]["competitive_position"]["label"],
            "Strong",
        )
        cache_write.assert_called_once_with(
            "feature-12b",
            _assessment_context(),
            {"status": "ok", "indicators": result["indicators"]},
        )

    def test_two_rejected_eligible_indicators_share_one_recovery_request(self):
        eligible = {"risk", "competitive_position"}
        primary_indicators = {
            "risk": _valid_indicators()["risk"],
            "competitive_position": _valid_indicators()["competitive_position"],
        }
        primary_indicators["risk"]["label"] = "Very High"
        primary_indicators["competitive_position"]["evidence"] = []
        recovered = {
            "risk": _valid_indicators()["risk"],
            "competitive_position": _valid_indicators()["competitive_position"],
        }
        context = _assessment_context()
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=json.dumps(primary_indicators),
        ), patch(
            "investment_research.gemini_provider._request_qualitative_recovery_model",
            return_value=json.dumps(recovered),
        ) as recovery, patch("investment_research.gemini_provider.cache.write"):
            result = generate_qualitative_assessment(
                context, eligible_indicators=eligible
            )

        recovery.assert_called_once_with(context, "test-key", eligible)
        self.assertEqual(set(result["indicators"]), eligible)

    def test_malformed_recovery_keeps_valid_primary_indicator_and_is_not_retried(self):
        primary = {
            "risk": _valid_indicators()["risk"],
            "competitive_position": {"label": "Strong", "drivers": [], "evidence": []},
        }
        context = _assessment_context()
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=json.dumps(primary),
        ), patch(
            "investment_research.gemini_provider._request_qualitative_recovery_model",
            return_value=json.dumps({
                "competitive_position": {
                    "label": "Strong",
                    "drivers": ["Only one driver."],
                    "evidence": ["Peer comparison supports the claim."],
                },
            }),
        ) as recovery, patch("investment_research.gemini_provider.cache.write") as cache_write:
            result = generate_qualitative_assessment(
                context,
                eligible_indicators={"risk", "competitive_position"},
            )

        recovery.assert_called_once()
        self.assertEqual(set(result["indicators"]), {"risk"})
        self.assertEqual(result["indicators"]["risk"]["label"], "Medium")
        cache_write.assert_not_called()

    def test_primary_and_recovery_each_make_at_most_one_request(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            side_effect=RuntimeError("503 service unavailable"),
        ) as primary, patch(
            "investment_research.gemini_provider._request_qualitative_recovery_model",
            return_value=json.dumps(_valid_indicators()),
        ) as recovery, patch("investment_research.gemini_provider.cache.write"):
            result = generate_qualitative_assessment(_assessment_context())

        primary.assert_called_once_with(_assessment_context(), "test-key")
        recovery.assert_called_once_with(
            _assessment_context(),
            "test-key",
            {"risk", "market_environment", "competitive_position"},
        )
        self.assertEqual(set(result["indicators"]), set(_valid_indicators()))

    def test_recovery_never_requests_indicator_without_eligible_evidence(self):
        context = _assessment_context()
        context["market_review"] = {"status": "unavailable", "review": None}
        primary = {
            "risk": _valid_indicators()["risk"],
            "competitive_position": _valid_indicators()["competitive_position"],
        }
        primary["competitive_position"]["drivers"] = ["Too few drivers."]
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=json.dumps(primary),
        ), patch(
            "investment_research.gemini_provider._request_qualitative_recovery_model",
            return_value=json.dumps({
                "competitive_position": _valid_indicators()["competitive_position"],
            }),
        ) as recovery, patch("investment_research.gemini_provider.cache.write"):
            result = assessment.build_stock_assessment(context)

        recovery.assert_called_once()
        self.assertNotIn("market_environment", recovery.call_args.args[2])
        self.assertEqual(result["indicators"]["market_environment"]["label"], "N/A")
        self.assertEqual(result["indicators"]["competitive_position"]["label"], "Strong")

    def test_malformed_raw_indicator_stays_na_without_rejecting_its_peers(self):
        malformed_responses = (
            ("risk", lambda item: item["drivers"].__setitem__(
                0, "Risk from debt, execution, legal, funding, suppliers, customers, tech, ops, concentration may all increase further."
            )),
            ("market_environment", lambda item: item.__setitem__("label", "Very Favourable")),
            ("competitive_position", lambda item: item.__setitem__("evidence", [" "])),
        )
        for malformed_key, corrupt in malformed_responses:
            with self.subTest(indicator=malformed_key):
                raw_indicators = _valid_indicators()
                corrupt(raw_indicators[malformed_key])
                with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
                    "investment_research.gemini_provider.cache.read", return_value=None
                ), patch(
                    "investment_research.gemini_provider._request_qualitative_assessment_model",
                    return_value=json.dumps(raw_indicators),
                ), patch(
                    "investment_research.gemini_provider._request_qualitative_recovery_model",
                    return_value="{}",
                ), patch("investment_research.gemini_provider.cache.write"):
                    result = assessment.build_stock_assessment(_assessment_context())

                for key in ("risk", "market_environment", "competitive_position"):
                    if key == malformed_key:
                        self.assertEqual(result["indicators"][key]["label"], "N/A")
                        self.assertEqual(
                            result["indicators"][key]["drivers"],
                            ["Qualitative assessment temporarily unavailable."],
                        )
                    else:
                        self.assertEqual(
                            result["indicators"][key]["label"],
                            _valid_indicators()[key]["label"],
                        )

    def test_valid_response_maps_all_hidden_scores_and_merges_eight_indicators(self):
        model_indicators = _valid_indicators()
        with patch(
            "investment_research.assessment.gemini_provider.generate_qualitative_assessment",
            return_value={"status": "ok", "indicators": model_indicators},
        ):
            result = assessment.build_stock_assessment(_assessment_context())

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["indicators"]), 8)
        self.assertEqual(result["indicators"]["risk"]["score"], 1)
        self.assertEqual(result["indicators"]["market_environment"]["score"], 1)
        self.assertEqual(result["indicators"]["competitive_position"]["score"], 1)
        for key in ("risk", "market_environment", "competitive_position"):
            self.assertEqual(result["indicators"][key]["components"], {})
            self.assertEqual(result["indicators"][key]["evidence"], model_indicators[key]["evidence"])

    def test_all_label_mappings_are_python_owned(self):
        expected_scores = {
            "risk": {"Low": 0, "Medium": 1, "High": 2},
            "market_environment": {"Unfavourable": -1, "Neutral": 0, "Favourable": 1},
            "competitive_position": {"Weak": -1, "Moderate": 0, "Strong": 1},
        }
        for key, scores in expected_scores.items():
            for label, score in scores.items():
                with self.subTest(key=key, label=label):
                    indicators = _valid_indicators()
                    indicators[key]["label"] = label
                    with patch(
                        "investment_research.assessment.gemini_provider.generate_qualitative_assessment",
                        return_value={"status": "ok", "indicators": indicators},
                    ):
                        result = assessment.build_stock_assessment(_assessment_context())
                    self.assertEqual(result["indicators"][key]["score"], score)

    def test_provider_rejects_invalid_label_without_losing_other_indicators(self):
        invalid = _valid_indicators()
        invalid["risk"]["label"] = "Very High"
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=json.dumps(invalid),
        ), patch(
            "investment_research.gemini_provider._request_qualitative_recovery_model",
            return_value="{}",
        ), patch("investment_research.gemini_provider.cache.write") as cache_write:
            result = generate_qualitative_assessment(_assessment_context())

        self.assertEqual(result["status"], "ok")
        self.assertNotIn("risk", result["indicators"])
        self.assertIn("market_environment", result["indicators"])
        cache_write.assert_not_called()

    def test_missing_drivers_or_evidence_rejects_only_malformed_indicator(self):
        for field, value in (("drivers", []), ("evidence", [])):
            with self.subTest(field=field):
                invalid = _valid_indicators()
                invalid["market_environment"][field] = value
                with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
                    "investment_research.gemini_provider.cache.read", return_value=None
                ), patch(
                    "investment_research.gemini_provider._request_qualitative_assessment_model",
                    return_value=json.dumps(invalid),
                ), patch(
                    "investment_research.gemini_provider._request_qualitative_recovery_model",
                    return_value="{}",
                ):
                    result = generate_qualitative_assessment(_assessment_context())
                self.assertNotIn("market_environment", result["indicators"])
                self.assertIn("risk", result["indicators"])

    def test_overlong_driver_rejects_only_affected_indicator(self):
        invalid = _valid_indicators()
        invalid["risk"]["drivers"][0] = "A " + "very " * 20 + "long risk driver."
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=json.dumps(invalid),
        ), patch(
            "investment_research.gemini_provider._request_qualitative_recovery_model",
            return_value="{}",
        ):
            result = generate_qualitative_assessment(_assessment_context())
        self.assertNotIn("risk", result["indicators"])
        self.assertIn("market_environment", result["indicators"])

    def test_unavailable_gemini_leaves_12a_available_and_12b_na(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model"
        ) as request:
            result = assessment.build_stock_assessment(_assessment_context())

        self.assertEqual(result["status"], "ok")
        for key in ("valuation", "financial_quality", "growth", "volatility", "expectations"):
            self.assertIn("label", result["indicators"][key])
        for key in ("risk", "market_environment", "competitive_position"):
            self.assertEqual(result["indicators"][key]["label"], "N/A")
        request.assert_not_called()

    def test_insufficient_prior_evidence_returns_na_without_calling_gemini(self):
        context = {
            "ticker": "EXM",
            "company": {"name": "Example Corp", "sector": "Technology"},
        }
        with patch(
            "investment_research.assessment.gemini_provider.generate_qualitative_assessment"
        ) as generate:
            result = assessment.build_stock_assessment(context)

        for key in ("risk", "market_environment", "competitive_position"):
            self.assertEqual(result["indicators"][key]["label"], "N/A")
        generate.assert_not_called()

    def test_eligible_evidence_with_provider_unavailable_is_not_mislabeled_insufficient(self):
        context = {
            "company": {"name": "Example Corp", "sector": "Energy"},
            "company_analysis": {
                "analysis": {
                    "key_factors_to_watch": [
                        "Regulatory approvals affect deployment timing.",
                        "Capital spending precedes commercial operations.",
                    ],
                    "peer_positioning": "Available peer evidence provides competitive context.",
                },
            },
        }
        with patch(
            "investment_research.assessment.gemini_provider.generate_qualitative_assessment",
            return_value={"status": "unavailable", "indicators": {}},
        ) as generate:
            result = assessment.build_stock_assessment(context)

        generate.assert_called_once()
        self.assertEqual(
            result["indicators"]["risk"]["drivers"][0],
            "Qualitative assessment temporarily unavailable.",
        )
        self.assertEqual(
            result["indicators"]["competitive_position"]["drivers"][0],
            "Qualitative assessment temporarily unavailable.",
        )
        self.assertEqual(
            result["indicators"]["market_environment"]["drivers"][0],
            "Insufficient evidence from previously collected features.",
        )

    def test_feature10_unavailable_does_not_block_feature9_risk_or_peer_evidence(self):
        context = {
            "company": {"name": "Example Corp", "sector": "Energy"},
            "company_analysis": {
                "analysis": {
                    "key_factors_to_watch": ["Deployment execution remains uncertain."],
                    "peer_positioning": "Peer comparisons show mixed operating performance.",
                },
            },
            "market_review": {
                "status": "unavailable",
                "review": None,
            },
        }
        with patch(
            "investment_research.assessment.gemini_provider.generate_qualitative_assessment",
            return_value={"status": "unavailable", "indicators": {}},
        ) as generate:
            result = assessment.build_stock_assessment(context)

        called_context = generate.call_args.args[0]
        self.assertTrue(assessment._qualitative_evidence_available(called_context, "risk"))
        self.assertTrue(
            assessment._qualitative_evidence_available(called_context, "competitive_position")
        )
        self.assertFalse(
            assessment._qualitative_evidence_available(called_context, "market_environment")
        )
        self.assertEqual(
            result["indicators"]["market_environment"]["label"],
            "N/A",
        )
        self.assertEqual(
            result["indicators"]["risk"]["drivers"][0],
            "Qualitative assessment temporarily unavailable.",
        )

    def test_feature9_unavailable_leaves_market_evidence_available(self):
        context = {
            "company": {"name": "Example Energy", "sector": "Energy"},
            "company_analysis": {
                "status": "unavailable",
                "analysis": None,
            },
            "market_review": {
                "status": "ok",
                "review": {
                    "industry_overview": "Power demand is rising.",
                    "market_outlook": "Demand remains supportive.",
                    "growth_drivers": ["Data centers add electricity demand."],
                    "competitive_dynamics": ["Competing capacity affects market position."],
                    "industry_risks": ["Permitting may delay new deployment."],
                    "company_implications": ["Regulatory timing shapes commercialization."],
                },
            },
        }
        with patch(
            "investment_research.assessment.gemini_provider.generate_qualitative_assessment",
            return_value={"status": "unavailable", "indicators": {}},
        ) as generate:
            result = assessment.build_stock_assessment(context)

        called_context = generate.call_args.args[0]
        for key in ("risk", "market_environment", "competitive_position"):
            self.assertTrue(assessment._qualitative_evidence_available(called_context, key))
            self.assertEqual(
                result["indicators"][key]["drivers"][0],
                "Qualitative assessment temporarily unavailable.",
            )

    def test_12a_results_are_unchanged_when_12b_raises(self):
        context = _assessment_context()
        original_12a = {
            "valuation": assessment.assess_valuation(context),
            "financial_quality": assessment.assess_financial_quality(context),
            "growth": assessment.assess_growth(context),
            "volatility": assessment.assess_volatility(context),
            "expectations": assessment.assess_expectations(context),
        }
        with patch(
            "investment_research.assessment.gemini_provider.generate_qualitative_assessment",
            side_effect=RuntimeError("provider unavailable"),
        ):
            result = assessment.build_stock_assessment(context)

        for key, expected in original_12a.items():
            self.assertEqual(result["indicators"][key], expected)

    def test_cache_is_written_only_for_a_complete_valid_response(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.gemini_provider.cache.read", return_value=None
        ), patch(
            "investment_research.gemini_provider._request_qualitative_assessment_model",
            return_value=json.dumps(_valid_indicators()),
        ), patch("investment_research.gemini_provider.cache.write") as cache_write:
            result = generate_qualitative_assessment(_assessment_context())

        self.assertEqual(set(result["indicators"]), {
            "risk", "market_environment", "competitive_position",
        })
        cache_write.assert_called_once()
        self.assertEqual(cache_write.call_args.args[0], "feature-12b")
        self.assertEqual(cache_write.call_args.args[1], _assessment_context())

    def test_context_uses_only_previous_feature_outputs(self):
        context = assessment.build_qualitative_context(_assessment_context())
        self.assertEqual(context["ticker"], "EXM")
        self.assertEqual(context["financial_snapshot"]["revenue_growth"], 12.0)
        self.assertEqual(context["market_review"]["tailwinds"], ["Cloud adoption supports demand."])
        self.assertEqual(context["market_review"]["company_implications"], [
            "Demand may change.", "Execution matters.", "Competition matters.",
        ])
        self.assertEqual(context["company_analysis"]["key_risks"], [
            "Execution against growth plans", "Customer retention",
        ])
        self.assertEqual(context["peer_context"]["peer_names"], ["PEER1", "PEER2"])
        self.assertEqual(context["market_review"]["sources"][0]["id"], "S1")

    def test_pre_revenue_and_market_fit_evidence_reach_existing_12b_indicators(self):
        source = _assessment_context()
        source["financials"]["income"].update({
            "revenue": [0.0],
            "revenue_status": ["valid_zero"],
            "revenue_stage": "pre_revenue",
        })
        source["market_review"]["review"]["company_implications"] = [
            "Slow approvals may delay commercialization.",
        ]
        context = assessment.build_qualitative_context(source)

        self.assertEqual(context["financial_snapshot"]["revenue_stage"], "pre_revenue")
        self.assertEqual(context["financial_snapshot"]["revenue_status"], "valid_zero")
        self.assertEqual(
            context["market_review"]["company_implications"],
            ["Slow approvals may delay commercialization."],
        )
        self.assertTrue(assessment._qualitative_evidence_available(context, "risk"))
        self.assertTrue(assessment._qualitative_evidence_available(context, "market_environment"))
        self.assertTrue(assessment._qualitative_evidence_available(context, "competitive_position"))


if __name__ == "__main__":
    unittest.main()
