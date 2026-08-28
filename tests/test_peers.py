import io
import unittest
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

from investment_research import display, peers


class TestPeerComparison(unittest.TestCase):

    def test_target_company_summary_and_correct_pe_direction(self):
        df = pd.DataFrame(
            {
                "AAPL": [5.0, 25.0, 35.5],
                "MSFT": [10.0, 30.0, 27.3],
                "GOOGL": [8.0, 20.0, 17.4],
                "AMZN": [9.5, 21.0, 21.0],
            },
            index=["Revenue Growth", "Operating Margin", "P/E"],
        )

        summary = peers._build_factual_summary("AAPL", df)

        self.assertTrue(summary[0].startswith("AAPL has "))
        self.assertIn("higher operating margin", summary[0])
        self.assertIn("Its P/E is higher than all 3 selected peers.", summary[1])

    def test_missing_peer_values_are_excluded_from_counts(self):
        df = pd.DataFrame(
            {
                "NVDA": [32.4, 20.0, 32.4],
                "AMD": [10.0, 15.0, 121.2],
                "AVGO": [8.0, 16.0, 59.5],
                "INTC": [np.nan, np.nan, np.nan],
            },
            index=["Revenue Growth", "Operating Margin", "P/E"],
        )

        summary = peers._build_factual_summary("NVDA", df)

        self.assertIn("both peers with available P/E data", summary[1])
        self.assertNotIn("all 2 selected peers", summary[1])

    def test_nan_values_are_displayed_as_na(self):
        self.assertEqual(display.format_growth(float("nan")), "N/A")
        self.assertEqual(display.format_percent(float("nan")), "N/A")
        self.assertEqual(display.format_price(float("nan")), "N/A")

    def test_shortened_description_stops_at_complete_sentences(self):
        text = (
            "This is the first sentence about the business. "
            "This is the second sentence. "
            "This is the third sentence. "
            "This is the fourth sentence. "
            "This is the fifth sentence that should be excluded."
        )
        shortened = display.shorten_description(text, max_sentences=4)
        self.assertFalse(shortened.endswith("..."))
        self.assertTrue(shortened.endswith("sentence."))
        self.assertEqual(shortened.count("."), 4)

    def test_negative_valuation_multiples_are_unavailable(self):
        df = pd.DataFrame(
            {
                "NFLX": [15.9, 29.5, 41.3, 0.8, 40.0, 20.0, 18.0],
                "DIS": [3.4, 14.6, 11.3, 0.42, 25.0, 15.0, 11.0],
                "CMCSA": [0.0, 16.7, 20.6, 0.61, 22.0, 14.0, 9.0],
                "PARA": [168.6, -151.8, -279.2, 1.32, -0.2, -0.5, -0.6],
            },
            index=["Revenue Growth", "Operating Margin", "ROE", "Debt/Equity", "P/E", "Forward P/E", "EV/EBITDA"],
        )
        summary = peers._build_factual_summary("NFLX", df)
        self.assertIn("available P/E data", summary[1])

        result = {"available": True, "tickers": ["NFLX", "DIS", "CMCSA", "PARA"], "df": df, "summary": summary}
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            display.print_peer_comparison(result)
        output = buffer.getvalue()
        self.assertIn("N/A", output)

    def test_positive_valuation_multiples_remain_valid(self):
        df = pd.DataFrame(
            {
                "AAPL": [15.0, 22.0, 38.0, 0.7, 35.5, 28.0, 22.0],
                "MSFT": [9.0, 18.0, 30.0, 0.4, 30.0, 25.0, 18.5],
                "GOOGL": [6.5, 15.0, 24.0, 0.55, 18.4, 17.0, 16.2],
                "AMZN": [12.0, 19.0, 33.0, 0.8, 21.0, 18.0, 17.5],
            },
            index=["Revenue Growth", "Operating Margin", "ROE", "Debt/Equity", "P/E", "Forward P/E", "EV/EBITDA"],
        )
        summary = peers._build_factual_summary("AAPL", df)
        self.assertIn("all 3 selected peers", summary[1])

    def test_negative_operating_margin_and_growth_stay_valid(self):
        self.assertEqual(display.format_percent(-151.8), "-151.8%")
        self.assertEqual(display.format_percent(-279.2), "-279.2%")
        self.assertEqual(display.format_growth(-20.0), "-20.0%")

    def test_negative_zero_formats_as_zero(self):
        self.assertEqual(display.format_growth(-0.0), "0.0%")
        self.assertEqual(display.format_percent(-0.0), "0.0%")

        df = pd.DataFrame(
            {
                "NFLX": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "DIS": [-0.0, -0.0, -0.0, -0.0, -0.0, -0.0, -0.0],
                "CMCSA": [1.0, 2.0, 3.0, 0.4, 1.5, 2.5, 3.5],
                "PARA": [5.0, 6.0, 7.0, 0.9, 6.0, 7.0, 8.0],
            },
            index=["Revenue Growth", "Operating Margin", "ROE", "Debt/Equity", "P/E", "Forward P/E", "EV/EBITDA"],
        )
        result = {"available": True, "tickers": ["NFLX", "DIS", "CMCSA", "PARA"], "df": df, "summary": ["NFLX has higher revenue growth than 1 of its 3 selected peers."]}
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            display.print_peer_comparison(result)
        output = buffer.getvalue()
        self.assertNotIn("-0.0%", output)
        self.assertNotIn("-0.0x", output)

    def test_summary_uses_selected_peers_for_all_valid_data(self):
        df = pd.DataFrame(
            {
                "NFLX": [15.9, 29.5, 41.3, 0.8, 40.0, 20.0, 18.0],
                "DIS": [3.4, 14.6, 11.3, 0.42, 25.0, 15.0, 11.0],
                "CMCSA": [0.0, 16.7, 20.6, 0.61, 22.0, 14.0, 9.0],
                "PARA": [168.6, -151.8, -279.2, 1.32, 12.0, 8.0, 7.0],
            },
            index=["Revenue Growth", "Operating Margin", "ROE", "Debt/Equity", "P/E", "Forward P/E", "EV/EBITDA"],
        )
        summary = peers._build_factual_summary("NFLX", df)
        self.assertTrue(any("selected peers" in sentence for sentence in summary))

    def test_summary_uses_available_data_when_some_peers_are_missing(self):
        df = pd.DataFrame(
            {
                "NVDA": [32.4, 20.0, 32.4, 0.7, 32.4, 16.0, 18.0],
                "AMD": [10.0, 15.0, 121.2, 0.9, 121.2, 29.5, 18.7],
                "AVGO": [8.0, 16.0, 59.5, 0.6, 59.5, 20.4, 15.0],
                "INTC": [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
            },
            index=["Revenue Growth", "Operating Margin", "ROE", "Debt/Equity", "P/E", "Forward P/E", "EV/EBITDA"],
        )
        summary = peers._build_factual_summary("NVDA", df)
        self.assertTrue(any("available P/E data" in sentence for sentence in summary))


if __name__ == "__main__":
    unittest.main()
