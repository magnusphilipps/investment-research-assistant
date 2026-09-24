import unittest

from investment_research.assessment import build_stock_assessment, assess_valuation


class TestFeature12A(unittest.TestCase):
    def test_build_stock_assessment_returns_all_five_indicators(self):
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
        self.assertEqual(sorted(result["indicators"].keys()), ["expectations", "financial_quality", "growth", "valuation", "volatility"])
        for indicator in result["indicators"].values():
            self.assertIn("label", indicator)
            self.assertIn("score", indicator)
            self.assertIsInstance(indicator["drivers"], list)
            self.assertIn("components", indicator)
            self.assertIn("evidence", indicator)

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


if __name__ == "__main__":
    unittest.main()
