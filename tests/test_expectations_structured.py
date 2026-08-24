import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

from investment_research import expectations


class TestExpectationsStructured(unittest.TestCase):

    @patch("investment_research.expectations.yf")
    def test_structured_recommendations_parsed(self, mock_yf):
        # Mock recommendations DataFrame with structured count columns
        recs = pd.DataFrame(
            {
                'strongBuy': [10, 10],
                'buy': [49, 48],
                'hold': [2, 2],
                'sell': [1, 1],
                'strongSell': [0, 0],
            },
            index=['0m', '-1m']
        )
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.recommendations = recs
        mock_ticker.revenue_estimate = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker

        res = expectations.get_analyst_expectations('NVDA')
        counts = res['recommendations']['counts']
        self.assertEqual(counts['Strong Buy'], 10)
        self.assertEqual(counts['Buy'], 49)
        self.assertEqual(counts['Hold'], 2)
        self.assertEqual(counts['Sell'], 1)
        self.assertEqual(counts['Strong Sell'], 0)
        self.assertEqual(res['recommendations']['consensus'], 'Buy')

    @patch("investment_research.expectations.yf")
    def test_revenue_estimate_parsing(self, mock_yf):
        # Mock revenue_estimate DataFrame with '0y' and '+1y' rows
        rev = pd.DataFrame(
            {
                'avg': [395400000000.0, 569500000000.0],
                'growth': [0.831, 0.44],
            },
            index=['0y', '+1y']
        )
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.recommendations = pd.DataFrame()
        mock_ticker.revenue_estimate = rev
        mock_yf.Ticker.return_value = mock_ticker

        res = expectations.get_analyst_expectations('NVDA')
        cy = res['revenue_estimates']['current_year']
        ny = res['revenue_estimates']['next_year']
        self.assertAlmostEqual(cy['revenue'], 395400000000.0)
        self.assertAlmostEqual(cy['growth'], 0.831)
        self.assertAlmostEqual(ny['revenue'], 569500000000.0)
        self.assertAlmostEqual(ny['growth'], 0.44)


if __name__ == '__main__':
    unittest.main()
