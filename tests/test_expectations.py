import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

from investment_research import expectations


class TestExpectations(unittest.TestCase):

    @patch("investment_research.expectations.yf")
    def test_parses_price_targets_and_upside(self, mock_yf):
        # Prepare mock Ticker with info containing price and targets
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "currentPrice": 200.0,
            "targetMeanPrice": 240.0,
            "targetMedianPrice": 242.0,
            "targetHighPrice": 285.0,
            "targetLowPrice": 190.0,
            "numberOfAnalystOpinions": 38,
        }
        # No recommendations DataFrame in this simple test
        mock_ticker.recommendations = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker

        res = expectations.get_analyst_expectations("MOCK")

        self.assertIn("price_targets", res)
        pt = res["price_targets"]
        self.assertAlmostEqual(pt["current_price"], 200.0)
        self.assertAlmostEqual(pt["average_target"], 240.0)
        self.assertAlmostEqual(pt["median_target"], 242.0)
        self.assertAlmostEqual(pt["high_target"], 285.0)
        self.assertAlmostEqual(pt["low_target"], 190.0)
        self.assertEqual(pt["analysts"], 38)
        self.assertAlmostEqual(pt["implied_upside"], (240.0/200.0) - 1)

    @patch("investment_research.expectations.yf")
    def test_handles_missing_data(self, mock_yf):
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.recommendations = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker

        res = expectations.get_analyst_expectations("MISSING")
        pt = res["price_targets"]
        self.assertIsNone(pt["current_price"])
        self.assertIsNone(pt["average_target"])
        self.assertIsNone(pt["implied_upside"])
        # summary should mention limited coverage
        self.assertTrue(any("limited" in s.lower() for s in res.get("summary", [])))


if __name__ == '__main__':
    unittest.main()
