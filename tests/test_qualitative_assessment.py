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
            },
            "sources": [{"id": "S1", "title": "Industry overview", "content": "Supplied market evidence."}],
        },
    }


class TestFeature12B(unittest.TestCase):
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
                ):
                    result = generate_qualitative_assessment(_assessment_context())
                self.assertNotIn("market_environment", result["indicators"])
                self.assertIn("risk", result["indicators"])

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
        self.assertEqual(context["company_analysis"]["key_risks"], [
            "Execution against growth plans", "Customer retention",
        ])
        self.assertEqual(context["peer_context"]["peer_names"], ["PEER1", "PEER2"])
        self.assertEqual(context["market_review"]["sources"][0]["id"], "S1")


if __name__ == "__main__":
    unittest.main()
