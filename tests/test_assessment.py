import re
import unittest
from unittest.mock import patch

from investment_research.assessment import build_stock_assessment, assess_valuation
from investment_research.assessment_scoring import compare_to_peer, is_concise_bullet


class TestCompareToPeer(unittest.TestCase):
    def test_discount_and_premium_thresholds(self):
        cases = (
            (0.70, 2.0),
            (0.85, 1.0),
            (1.00, 0.0),
            (1.15, -1.0),
            (1.30, -2.0),
        )
        for company_value, expected_score in cases:
            with self.subTest(company_value=company_value):
                self.assertEqual(compare_to_peer(company_value, 1.0), expected_score)

    def test_invalid_or_non_positive_values_return_none(self):
        for company_value, peer_median in (
            ("invalid", 1.0),
            (1.0, "invalid"),
            (None, 1.0),
            (1.0, None),
            (0.0, 1.0),
            (-1.0, 1.0),
            (1.0, 0.0),
            (1.0, -1.0),
            (float("nan"), 1.0),
            (1.0, float("inf")),
        ):
            with self.subTest(company_value=company_value, peer_median=peer_median):
                self.assertIsNone(compare_to_peer(company_value, peer_median))

    def test_dashboard_bullets_have_hard_length_and_single_sentence_limits(self):
        self.assertTrue(is_concise_bullet("One concise idea."))
        self.assertFalse(is_concise_bullet("x" * 91))
        self.assertFalse(is_concise_bullet("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"))
        self.assertFalse(is_concise_bullet("First complete idea. Second complete idea."))


class TestFeature12A(unittest.TestCase):
    def setUp(self):
        self.gemini_patch = patch(
            "investment_research.assessment.gemini_provider.generate_qualitative_assessment",
            return_value={"status": "unavailable", "indicators": {}},
        )
        self.gemini_patch.start()
        self.addCleanup(self.gemini_patch.stop)

    def test_build_stock_assessment_returns_all_eight_indicators(self):
        context = {
            "company": {"sector": "Technology", "industry": "Software"},
            "financials": {
                "income": {
                    "revenue": [1000.0],
                    "revenue_growth": [18.0],
                    "net_income": [120.0],
                    "op_margin": [22.0],
                },
                "cashflow": {
                    "free_cash_flow": [180.0],
                    "operating_cf": [220.0],
                },
            },
            "ratios": {
                "profitability": {"op_margin": 22.0},
                "strength": {"de_ratio": 0.9, "current_ratio": 1.7},
                "valuation": {"trailing_pe": 18.0, "forward_pe": 16.0, "ev_ebitda": 12.0},
            },
            "performance": {"annualized_volatility": 0.25, "beta": 1.0, "max_drawdown": 0.2},
            "analyst_expectations": {
                "revenue_estimates": {"next_year": {"growth": 12.0}},
                "recommendations": {"Strong Buy": 40, "Buy": 30, "Hold": 20, "Sell": 5, "Strong Sell": 5},
                "price_targets": {"implied_upside": 0.12},
            },
            "peer_comparison": {"df": {
                "P/E": [18.0, 20.0, 22.0],
                "Forward P/E": [15.0, 16.0, 17.0],
                "EV/EBITDA": [11.0, 12.0, 13.0],
                "Operating Margin": [20.0, 22.0, 24.0],
            }},
        }
        result = build_stock_assessment(context)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(sorted(result["indicators"].keys()), [
            "competitive_position", "expectations", "financial_quality", "growth",
            "market_environment", "risk", "valuation", "volatility",
        ])
        for indicator in result["indicators"].values():
            self.assertIn("label", indicator)
            self.assertIn("score", indicator)
            self.assertIsInstance(indicator["drivers"], list)
            self.assertIn("components", indicator)
            self.assertIn("evidence", indicator)
            for driver in indicator["drivers"]:
                self.assertLessEqual(len(driver), 90)
                self.assertLessEqual(len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", driver)), 14)

    def test_valuation_skips_negative_earnings_and_uses_sales_mode(self):
        context = {
            "company": {"sector": "Technology"},
            "financials": {
                "income": {
                    "revenue": [500.0],
                    "revenue_growth": [35.0],
                    "net_income": [-20.0],
                },
            },
            "ratios": {
                "valuation": {"ev_revenue": 2.2, "price_to_sales": 1.8},
            },
            "peer_comparison": {"df": {
                "EV/Revenue": [2.0, 2.4, 3.0],
                "Price/Sales": [1.7, 2.0, 2.4],
            }},
        }
        result = assess_valuation(context)
        self.assertEqual(result["label"], "Fair")
        self.assertIn("EV/Revenue", result["components"])
        self.assertEqual(result["evidence"]["valuation_mode"], "sales")

    def test_financial_quality_bank_path_uses_sector_aware_rules(self):
        context = {
            "company": {"sector": "Financial Services"},
            "financials": {
                "income": {"revenue": [1000.0], "op_margin": [18.0]},
                "cashflow": {"free_cash_flow": [120.0], "operating_cf": [200.0]},
            },
            "ratios": {"profitability": {"op_margin": 18.0}},
            "peer_comparison": {"df": {"Operating Margin": [15.0, 18.0, 20.0]}},
        }
        result = build_stock_assessment(context)["indicators"]["financial_quality"]
        self.assertIn(result["label"], {"Strong", "Moderate"})
        self.assertNotIn("current_ratio", result["components"])

    def test_expectations_handles_missing_target_and_rebalances_weight(self):
        context = {
            "analyst_expectations": {
                "revenue_estimates": {"next_year": {"growth": 7.0}},
                "recommendations": {"Buy": 50, "Hold": 25, "Sell": 25},
                "price_targets": {},
            }
        }
        result = build_stock_assessment(context)["indicators"]["expectations"]
        self.assertIn(result["label"], {"Positive", "Neutral"})
        self.assertIn("forward_revenue_growth", result["components"])


class TestPreRevenueAssessment(unittest.TestCase):
    def setUp(self):
        self.context = {
            "ticker": "OKLO",
            "company": {"name": "Oklo Inc.", "sector": "Industrials"},
            "financials": {
                "income": {
                    "revenue": [0.0, 0.0],
                    "revenue_status": ["valid_zero", "valid_zero"],
                    "revenue_stage": "pre_revenue",
                    "revenue_growth": [None],
                    "revenue_growth_status": ["not_meaningful"],
                    "net_income": [-100.0, -80.0],
                    "op_margin": [None, None],
                    "op_margin_status": ["not_meaningful", "not_meaningful"],
                },
                "cashflow": {"free_cash_flow": [-150.0], "operating_cf": [-100.0]},
            },
            "ratios": {
                "profitability": {"op_margin": None},
                "strength": {"de_ratio": 0.3, "current_ratio": 4.0},
                "valuation": {"trailing_pe": 25.0, "ev_revenue": 18.0, "price_to_sales": 20.0},
            },
            "peer_comparison": {"df": {
                "EV/Revenue": [10.0, 12.0, 15.0],
                "Price/Sales": [10.0, 15.0, 20.0],
                "Operating Margin": [10.0, 15.0, 20.0],
            }},
            "analyst_expectations": {
                "revenue_estimates": {"next_year": {"growth": 100.0}},
                "recommendations": {"Buy": 2, "Hold": 1},
            },
        }

    def test_pre_revenue_metrics_are_excluded_and_valuation_is_not_forced(self):
        valuation = assess_valuation(self.context)
        growth = build_stock_assessment(self.context)["indicators"]["growth"]
        expectations = build_stock_assessment(self.context)["indicators"]["expectations"]
        quality_context = {
            **self.context,
            "ratios": {"de_ratio": 0.3, "current_ratio": 4.0},
        }
        quality = build_stock_assessment(quality_context)["indicators"]["financial_quality"]

        self.assertEqual(valuation["label"], "N/A")
        self.assertIn("pre-revenue", valuation["drivers"][0].lower())
        self.assertEqual(valuation["evidence"]["revenue_stage"], "pre_revenue")
        self.assertEqual(growth["label"], "N/A")
        self.assertEqual(growth["components"], {})
        self.assertEqual(growth["evidence"]["revenue_stage"], "pre_revenue")
        self.assertNotIn("forward_revenue_growth", expectations["components"])
        self.assertNotIn("fcf_margin", quality["components"])
        self.assertNotIn("operating_margin", quality["components"])
        self.assertTrue(any("not meaningful" in item for item in quality["evidence"]["excluded_components"]))

    def test_missing_revenue_is_unavailable_not_pre_revenue(self):
        context = {
            "financials": {"income": {"revenue": [None, None], "revenue_growth": [None]}},
        }
        result = build_stock_assessment(context)["indicators"]["growth"]
        self.assertEqual(result["label"], "N/A")
        self.assertNotIn("pre-revenue", result["drivers"][0])


if __name__ == "__main__":
    unittest.main()
