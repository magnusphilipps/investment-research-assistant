import unittest
from unittest.mock import patch

import pandas as pd

from investment_research import display
from investment_research.financials import _compute_income, get_ratios


class FinancialMetricStateTests(unittest.TestCase):
    def test_zero_missing_and_not_meaningful_income_states_are_distinct(self):
        columns = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31"])
        statement = pd.DataFrame(
            [
                [0.0, 0.0, None],
                [0.0, 0.0, None],
                [-50.0, -40.0, None],
                [-60.0, -45.0, None],
            ],
            index=["Total Revenue", "Gross Profit", "Operating Income", "Net Income"],
            columns=columns,
        )
        income = _compute_income(statement)

        self.assertEqual(income["revenue"][:2], [0.0, 0.0])
        self.assertEqual(income["revenue_status"], ["valid_zero", "valid_zero", "unavailable"])
        self.assertEqual(income["revenue_stage"], "pre_revenue")
        self.assertEqual(income["revenue_growth"], [None, None])
        self.assertEqual(income["revenue_growth_status"], ["not_meaningful", "unavailable"])
        self.assertEqual(income["gross_margin_status"], ["not_meaningful", "not_meaningful", "unavailable"])
        self.assertEqual(income["op_margin_status"], ["not_meaningful", "not_meaningful", "unavailable"])

    def test_loss_makes_trailing_earnings_multiples_not_meaningful(self):
        statements = {
            "income": {
                "years": ["2025"],
                "revenue": [0.0],
                "revenue_status": ["valid_zero"],
                "revenue_stage": "pre_revenue",
                "net_income": [-10.0],
                "eps_diluted": [-0.5],
                "op_margin": [None],
                "op_margin_status": ["not_meaningful"],
            },
            "balance": {"equity": 100.0},
        }
        info = {
            "trailingPE": 50.0,
            "forwardPE": 25.0,
            "pegRatio": 2.0,
            "enterpriseValue": 1000.0,
            "ebitda": -20.0,
            "priceToBook": 3.0,
        }
        with patch("investment_research.financials.yf.Ticker") as ticker:
            ticker.return_value.info = info
            ratios = get_ratios("OKLO", statements)

        self.assertEqual(ratios["profitability"]["net_margin_status"], "not_meaningful")
        self.assertIsNone(ratios["profitability"]["net_margin"])
        self.assertIsNone(ratios["valuation"]["trailing_pe"])
        self.assertEqual(ratios["valuation"]["trailing_pe_status"], "not_meaningful")
        self.assertIsNone(ratios["valuation"]["peg"])
        self.assertEqual(ratios["valuation"]["peg_status"], "not_meaningful")
        self.assertIsNone(ratios["valuation"]["ev_ebitda"])
        self.assertEqual(ratios["valuation"]["ev_ebitda_status"], "not_meaningful")
        self.assertEqual(ratios["valuation"]["forward_pe"], 25.0)

    def test_income_display_identifies_pre_revenue_and_not_meaningful_metrics(self):
        income = {
            "years": ["2025", "2024"],
            "revenue": [0.0, 0.0],
            "revenue_growth": [None],
            "revenue_growth_status": ["not_meaningful"],
            "revenue_stage": "pre_revenue",
            "gross_profit": [0.0, 0.0],
            "gross_margin": [None, None],
            "gross_margin_status": ["not_meaningful", "not_meaningful"],
            "op_income": [-50.0, -40.0],
            "op_margin": [None, None],
            "op_margin_status": ["not_meaningful", "not_meaningful"],
            "net_income": [-60.0, -45.0],
            "eps_diluted": [None, None],
            "shares_diluted": [None, None],
            "acceleration": "Unavailable",
        }
        with patch("builtins.print") as printer:
            display.print_income_statement({"income": income})

        output = " ".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("Pre-revenue", output)
        self.assertIn("N/M", output)


if __name__ == "__main__":
    unittest.main()
