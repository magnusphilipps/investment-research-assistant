import runpy
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from investment_research import ticker_resolution
from investment_research.ticker_resolution import (
    SecurityCandidate,
    TickerResolution,
)


class TickerResolutionTests(unittest.TestCase):
    def setUp(self):
        ticker_resolution.clear_resolution_cache()
        ticker_resolution.fetcher.clear_yahoo_info_cache()

    def _mock_search(self, quotes):
        return patch(
            "investment_research.ticker_resolution.yf.Search",
            return_value=SimpleNamespace(quotes=quotes),
        )

    def _quote(self, ticker, name, exchange, score=20_000):
        return {
            "symbol": ticker,
            "longname": name,
            "quoteType": "EQUITY",
            "exchDisp": exchange,
            "score": score,
        }

    def test_exact_us_symbol_is_unchanged(self):
        with self._mock_search([
            self._quote("AAPL", "Apple Inc.", "NASDAQ"),
            self._quote("AAPLW", "Apple Inc. Warrant", "NASDAQ"),
        ]):
            result = ticker_resolution.resolve_security_input("aapl")

        self.assertEqual(result, TickerResolution(status="resolved", ticker="AAPL"))

    def test_existing_exchange_symbol_is_unchanged_without_search(self):
        with patch("investment_research.ticker_resolution.yf.Search") as search:
            result = ticker_resolution.resolve_security_input("  barc.l ")

        self.assertEqual(result, TickerResolution(status="resolved", ticker="BARC.L"))
        search.assert_not_called()

    def test_company_name_resolves_when_provider_returns_one_strong_listing(self):
        with self._mock_search([
            self._quote("BARC.L", "Barclays PLC", "London"),
        ]) as search:
            result = ticker_resolution.resolve_security_input("Barclays")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.ticker, "BARC.L")
        search.assert_called_once()

    def test_unsuffixed_ticker_prefers_its_unique_market_specific_match(self):
        with self._mock_search([
            self._quote("BCS", "Barclays PLC", "NYSE", 20_900),
            self._quote("BARC.L", "Barclays PLC", "London", 20_500),
        ]):
            result = ticker_resolution.resolve_security_input("BARC")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.ticker, "BARC.L")

    def test_rwe_uses_provider_rank_for_the_clear_german_listing(self):
        with self._mock_search([
            self._quote("RWE.DE", "RWE Aktiengesellschaft", "XETRA", 20_246),
            self._quote("RWE.F", "RWE Aktiengesellschaft", "Frankfurt", 20_016),
            self._quote("RWEOY", "RWE Aktiengesellschaft", "OTC Markets", 20_069),
        ]):
            result = ticker_resolution.resolve_security_input("RWE")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.ticker, "RWE.DE")

    def test_unilever_returns_ambiguous_listings_without_guessing(self):
        with self._mock_search([
            self._quote("ULVR.L", "Unilever PLC", "London", 20_258),
            self._quote("UNA.AS", "Unilever N.V.", "Amsterdam", 20_250),
        ]):
            result = ticker_resolution.resolve_security_input("Unilever")

        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.ticker)
        self.assertEqual(
            [(item.ticker, item.company_name, item.exchange) for item in result.candidates],
            [
                ("ULVR.L", "Unilever PLC", "London"),
                ("UNA.AS", "Unilever N.V.", "Amsterdam"),
            ],
        )

    def test_ulvr_symbol_resolves_to_london_listing(self):
        with self._mock_search([
            self._quote("ULVR.L", "Unilever PLC", "London"),
        ]):
            result = ticker_resolution.resolve_security_input("ULVR")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.ticker, "ULVR.L")

    def test_unmatched_input_is_not_found(self):
        with self._mock_search([
            self._quote("AAPL", "Apple Inc.", "NASDAQ"),
        ]) as search:
            result = ticker_resolution.resolve_security_input("unknown nonsense")

        self.assertEqual(result.status, "not_found")
        self.assertEqual(search.call_args.args[0], "unknown nonsense")

    def test_successful_resolution_is_cached_using_normalized_input(self):
        with self._mock_search([
            self._quote("BARC.L", "Barclays PLC", "London"),
        ]) as search:
            first = ticker_resolution.resolve_security_input("  Barclays ")
            second = ticker_resolution.resolve_security_input("barclays")

        self.assertEqual(first, second)
        search.assert_called_once()

    def test_ambiguous_results_are_capped_at_three(self):
        with self._mock_search([
            self._quote("ULVR.L", "Unilever PLC", "London", 20_500),
            self._quote("UNA.AS", "Unilever N.V.", "Amsterdam", 20_400),
            self._quote("UL", "Unilever PLC", "NYSE", 20_300),
            self._quote("ULVR.F", "Unilever PLC", "Frankfurt", 20_200),
        ]):
            result = ticker_resolution.resolve_security_input("Unilever")

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(len(result.candidates), 3)

    def test_provider_failure_is_reported_as_resolution_error(self):
        with patch(
            "investment_research.ticker_resolution.yf.Search",
            side_effect=RuntimeError("provider unavailable"),
        ):
            with self.assertRaises(ticker_resolution.TickerResolutionError):
                ticker_resolution.resolve_security_input("Barclays")

    def test_unknown_app_input_does_not_start_analysis_or_research_providers(self):
        class FakeStreamlit:
            session_state = {}

            def set_page_config(self, **_kwargs):
                pass

            def title(self, *_args, **_kwargs):
                pass

            def write(self, *_args, **_kwargs):
                pass

            def markdown(self, *_args, **_kwargs):
                pass

            def html(self, *_args, **_kwargs):
                pass

            def form(self, *_args, **_kwargs):
                return nullcontext()

            def text_input(self, *_args, **_kwargs):
                return "unknown nonsense"

            def form_submit_button(self, *_args, **_kwargs):
                return True

            def error(self, message, *_args, **_kwargs):
                self.errors = getattr(self, "errors", []) + [message]

        fake_streamlit = FakeStreamlit()
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.ticker_resolution.resolve_security_input",
            return_value=TickerResolution(status="not_found"),
        ), patch("investment_research.main.get_company_info") as company_lookup, patch(
            "investment_research.main.build_report"
        ) as build_report, patch(
            "investment_research.gemini_provider.generate_analysis"
        ) as gemini_company, patch(
            "investment_research.gemini_provider.generate_market_review"
        ) as gemini_market, patch(
            "investment_research.gemini_provider.generate_bull_bear"
        ) as gemini_bull_bear, patch(
            "investment_research.tavily_provider.search"
        ) as tavily_search, patch(
            "investment_research.news.requests.get"
        ) as marketaux_request:
            runpy.run_path(str(app_path), run_name="ticker_resolution_invalid_test")

        self.assertIn(
            "Ticker or company not found. Check the symbol or company name and try again.",
            fake_streamlit.errors,
        )
        for provider in (
            company_lookup,
            build_report,
            gemini_company,
            gemini_market,
            gemini_bull_bear,
            tavily_search,
            marketaux_request,
        ):
            provider.assert_not_called()

    def test_selected_candidate_is_validated_once_and_report_receives_canonical_symbol(self):
        candidate = SecurityCandidate("BARC.L", "Barclays PLC", "London")

        class FakeStreamlit:
            session_state = {"ticker_resolution_candidates": (candidate,)}

            def set_page_config(self, **_kwargs):
                pass

            def title(self, *_args, **_kwargs):
                pass

            def write(self, *_args, **_kwargs):
                pass

            def markdown(self, *_args, **_kwargs):
                pass

            def html(self, *_args, **_kwargs):
                pass

            def form(self, *_args, **_kwargs):
                return nullcontext()

            def text_input(self, *_args, **_kwargs):
                return ""

            def form_submit_button(self, *_args, **_kwargs):
                return False

            def selectbox(self, _label, *, options, **_kwargs):
                return options[0]

            def button(self, _label, *, key, **_kwargs):
                return key == "analyse-selected-listing"

            def spinner(self, *_args, **_kwargs):
                return nullcontext()

            def empty(self):
                return FakePlaceholder()

            def error(self, *_args, **_kwargs):
                pass

        class FakePlaceholder:
            def container(self):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def caption(self, *_args, **_kwargs):
                pass

            def empty(self):
                pass

        fake_streamlit = FakeStreamlit()
        company = {"ticker": "BARC.L", "name": "Barclays PLC"}
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.main.get_company_info",
            return_value=company,
        ) as company_lookup, patch(
            "investment_research.main.build_report",
            return_value=None,
        ) as build_report, patch(
            "investment_research.ticker_resolution.yf.Search",
        ) as search:
            runpy.run_path(str(app_path), run_name="ticker_resolution_selection_test")

        company_lookup.assert_called_once_with("BARC.L")
        build_report.assert_called_once_with("BARC.L", preloaded_company=company)
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
