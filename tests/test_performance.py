import unittest
from unittest.mock import patch

import pandas as pd

from investment_research.performance import (
    _calculate_52_week_range,
    get_performance,
)


def history(start: str, end: str) -> pd.DataFrame:
    """Create predictable weekday prices for tests without network access."""
    dates = pd.date_range(start, end, freq="B")
    adjusted_prices = pd.Series(range(100, 100 + len(dates)), index=dates, dtype="float64")
    return pd.DataFrame({
        "Adj Close": adjusted_prices,
        "Close": adjusted_prices + 1,
        "High": adjusted_prices + 10,
        "Low": adjusted_prices - 10,
    })


class PerformanceTests(unittest.TestCase):
    def test_mature_company_has_all_periods_and_range(self):
        stock = history("2019-01-02", "2025-02-03")
        benchmark = history("2019-01-02", "2025-02-03")

        with patch("investment_research.performance.yf.Ticker") as ticker:
            ticker.side_effect = lambda symbol: type(
                "MockTicker", (), {"history": lambda self, **kwargs: stock if symbol in ("AAPL", "NFLX") else benchmark}
            )()
            result = get_performance("AAPL")
            nflx_result = get_performance("NFLX")

        self.assertIsNotNone(result)
        self.assertTrue(all(value is not None for value in result["returns"].values()))
        self.assertEqual(result["range"]["high"], float(stock["High"].iloc[-1]))
        window_start = stock.index[-1] - pd.DateOffset(weeks=52)
        expected_low = stock.loc[stock.index >= window_start, "Low"].min()
        self.assertEqual(result["range"]["low"], float(expected_low))
        self.assertNotEqual(result["range"]["high"], float(stock["Adj Close"].max()))
        self.assertIsNotNone(result["benchmark"]["5 Years"]["difference"])
        self.assertAlmostEqual(nflx_result["returns"]["1 Year"], result["returns"]["1 Year"])

    def test_short_history_returns_na_for_unavailable_periods(self):
        stock = history("2024-01-02", "2025-02-03")
        benchmark = history("2019-01-02", "2025-02-03")

        with patch("investment_research.performance.yf.Ticker") as ticker:
            ticker.side_effect = lambda symbol: type(
                "MockTicker", (), {"history": lambda self, **kwargs: stock if symbol == "OKLO" else benchmark}
            )()
            result = get_performance("OKLO")

        self.assertIsNotNone(result)
        self.assertIsNone(result["returns"]["3 Years"])
        self.assertIsNone(result["returns"]["5 Years"])
        self.assertIsNone(result["benchmark"]["3 Years"]["stock"])
        self.assertIsNone(result["benchmark"]["3 Years"]["benchmark"])
        self.assertIsNone(result["benchmark"]["3 Years"]["difference"])

    def test_incomplete_history_and_invalid_ticker(self):
        incomplete = history("2024-08-01", "2025-02-03")
        empty = pd.DataFrame(columns=["Adj Close", "Close", "High", "Low"])

        with patch("investment_research.performance.yf.Ticker") as ticker:
            ticker.side_effect = lambda symbol: type(
                "MockTicker", (), {"history": lambda self, **kwargs: incomplete if symbol == "NBIS" else empty}
            )()
            result = get_performance("NBIS")
            invalid = get_performance("INVALID")

        self.assertIsNone(result["returns"]["1 Year"])
        self.assertIsNone(invalid)

    def test_benchmark_failure_does_not_hide_stock_data(self):
        stock = history("2019-01-02", "2025-02-03")

        with patch("investment_research.performance.yf.Ticker") as ticker:
            def make_ticker(symbol):
                if symbol == "^GSPC":
                    raise RuntimeError("benchmark unavailable")
                return type("MockTicker", (), {"history": lambda self, **kwargs: stock})()

            ticker.side_effect = make_ticker
            result = get_performance("JPM")

        self.assertIsNotNone(result["returns"]["1 Year"])
        self.assertIsNone(result["benchmark"]["1 Year"]["benchmark"])

    def test_52_week_range_handles_empty_data(self):
        result = _calculate_52_week_range(pd.DataFrame())
        self.assertIsNone(result["current_price"])
        self.assertIsNone(result["high"])


if __name__ == "__main__":
    unittest.main()