from contextlib import redirect_stdout
import io
import unittest

from investment_research import display


class MarketPriceDisplayTests(unittest.TestCase):
    def test_formats_provider_currency_symbols_and_native_quotation_units(self):
        cases = (
            ("AAPL / USD", 123.45, "USD", "$123.45"),
            ("BARC.L / GBp", 123.45, "GBp", "123.45p"),
            ("BARC.L / GBX", 123.45, "GBX", "123.45p"),
            ("GBP-denominated listing", 123.45, "GBP", "£123.45"),
            ("RWE.DE / EUR", 123.45, "EUR", "€123.45"),
            ("Japanese stock / JPY", 12_345, "JPY", "¥12,345"),
            ("Unmapped currency", 123.45, "CAD", "CAD 123.45"),
        )

        for label, value, currency, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(display.format_market_price(value, currency), expected)

    def test_missing_values_and_unavailable_markers_are_safe(self):
        self.assertEqual(display.format_market_price(None, "USD"), "N/A")
        self.assertEqual(display.format_market_price("N/A", "USD"), "N/A")
        self.assertEqual(display.format_market_price("N/M", "USD"), "N/M")

    def test_percentages_remain_currency_independent(self):
        self.assertEqual(display.format_return(0.123), "+12.3%")
        self.assertEqual(display.format_pct_fraction(-0.045), "-4.5%")

    def test_unknown_currency_does_not_assume_usd(self):
        self.assertEqual(display.format_market_price(123.45), "123.45")

    def test_market_cap_uses_its_currency_and_existing_compact_scale(self):
        cases = (
            ("AAPL", 57_340_000_000, "USD", "$57.34 Billion"),
            ("BARC.L", 57_340_000_000, "GBP", "£57.34 Billion"),
            ("RWE.DE", 1_240_000_000_000, "EUR", "€1.24 Trillion"),
            ("GBP listing", 57_340_000_000, "GBP", "£57.34 Billion"),
            ("JPY listing", 5_730_000_000_000, "JPY", "¥5.73 Trillion"),
            ("Unknown currency", 57_340_000_000, "CAD", "CAD 57.34 Billion"),
        )

        for label, value, currency, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(display.format_market_cap(value, currency), expected)

        self.assertEqual(display.format_market_cap(None, "GBP"), "N/A")

    def test_terminal_price_sections_use_native_currency_and_keep_returns_as_percentages(self):
        output = io.StringIO()
        with redirect_stdout(output):
            display.print_stock_info({
                "name": "Barclays PLC",
                "ticker": "BARC.L",
                "price": 123.45,
                "market_cap": 57_340_000_000,
                "currency": "GBp",
                "market_cap_currency": "GBP",
            })
            display.print_performance(
                {
                    "returns": {"1 Month": 0.05},
                    "range": {"current_price": 123.45, "high": 150.0, "low": 100.0},
                    "benchmark": {},
                },
                currency="GBp",
            )
            display.print_analyst_expectations({
                "price_targets": {
                    "current_price": 123.45,
                    "average_target": 140.0,
                    "median_target": None,
                    "high_target": None,
                    "low_target": None,
                    "implied_upside": 0.134,
                    "currency": "GBp",
                },
                "recommendations": {},
                "revenue_estimates": {},
            })

        rendered = output.getvalue()
        self.assertIn("Share Price  :  123.45p", rendered)
        self.assertIn("Market Cap   :  £57.34 Billion", rendered)
        self.assertNotIn("Market Cap   :  $", rendered)
        self.assertIn("52-Week High", rendered)
        self.assertIn("140.00p", rendered)
        self.assertIn("+5.0%", rendered)
        self.assertIn("+13.4%", rendered)


if __name__ == "__main__":
    unittest.main()
