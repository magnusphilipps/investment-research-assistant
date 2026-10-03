from contextlib import ExitStack
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from investment_research import assessment, fetcher, main, peers


class InvalidTickerTests(unittest.TestCase):
    def test_company_metadata_includes_exchange_and_market_for_feature5(self):
        with patch("investment_research.fetcher.yf.Ticker") as ticker:
            ticker.return_value.info = {
                "symbol": "TEST.L",
                "longName": "Test Company",
                "exchange": "LSE",
                "market": "gb_market",
            }
            result = fetcher.get_stock_info("TEST.L")
        self.assertEqual(result["exchange"], "LSE")
        self.assertEqual(result["market"], "gb_market")

    def test_symbol_only_provider_response_is_not_a_resolved_security(self):
        with patch("investment_research.fetcher.yf.Ticker") as ticker:
            ticker.return_value.info = {"symbol": "NBA"}
            self.assertIsNone(fetcher.get_stock_info("NBA"))

    def test_http_404_from_company_lookup_is_treated_as_not_found(self):
        error = RuntimeError("provider details should not reach the user")
        error.response = SimpleNamespace(status_code=404)
        class ProviderTicker:
            @property
            def info(self):
                raise error

        with patch("investment_research.fetcher.yf.Ticker", return_value=ProviderTicker()):
            self.assertIsNone(fetcher.get_stock_info("NOTREAL"))

    def test_other_provider_errors_still_propagate(self):
        error = RuntimeError("provider unavailable")
        class ProviderTicker:
            @property
            def info(self):
                raise error

        with patch("investment_research.fetcher.yf.Ticker", return_value=ProviderTicker()):
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                fetcher.get_stock_info("AAPL")

    def test_fake_ticker_exits_before_any_analysis_features(self):
        downstream_paths = (
            "investment_research.main.display.print_stock_info",
            "investment_research.main.display.print_company_overview",
            "investment_research.main.display.print_income_statement",
            "investment_research.main.display.print_balance_sheet",
            "investment_research.main.display.print_cash_flow",
            "investment_research.main.display.print_ratios",
            "investment_research.main.display.print_performance",
            "investment_research.main.display.print_analyst_expectations",
            "investment_research.main.display.print_peer_comparison",
            "investment_research.main.display.print_news",
            "investment_research.main.display.print_ai_analysis",
            "investment_research.main.display.print_market_review",
            "investment_research.main.display.print_bull_bear_analysis",
            "investment_research.main.display.print_stock_assessment",
            "investment_research.main.financials.get_financial_statements",
            "investment_research.main.financials.get_ratios",
            "investment_research.main.peers.fetch_peer_comparison",
            "investment_research.main.performance.get_performance",
            "investment_research.main.expectations.get_analyst_expectations",
            "investment_research.main.news.get_company_news",
            "investment_research.main.analysis.get_ai_analysis",
            "investment_research.main.market_research.get_market_review",
            "investment_research.main.analysis.get_bull_bear_analysis",
            "investment_research.main.assessment.build_stock_assessment",
        )
        with patch("builtins.input", side_effect=["NBA", "quit"]), patch(
            "builtins.print"
        ), patch("investment_research.main.display.print_welcome"), patch(
            "investment_research.fetcher.yf.Ticker"
        ) as ticker, patch(
            "investment_research.main.display.print_error"
        ) as print_error, ExitStack() as stack:
            ticker.return_value.info = {"symbol": "NBA"}
            downstream = [stack.enter_context(patch(path)) for path in downstream_paths]
            main.run()

        print_error.assert_called_once_with(
            "Ticker not found. Check the symbol and try again."
        )
        for feature in downstream:
            feature.assert_not_called()

    def _run_valid_ticker(self, ticker_symbol, info):
        feature9 = {
            "status": "ok",
            "analysis": {
                "financial_performance": "Pre-revenue operations show early commercialization.",
                "financial_position": "Cash burn and capital spending remain relevant.",
                "valuation": "Traditional valuation metrics are not meaningful.",
                "share_price_and_expectations": "Price history remains limited.",
                "peer_positioning": "Peer evidence is available for context.",
                "recent_developments": "Regulatory approvals remain relevant.",
                "key_factors_to_watch": [
                    "Regulatory approvals affect deployment timing.",
                    "Capital spending continues before commercial revenue.",
                    "Customer adoption remains an execution factor.",
                ],
            },
        }
        feature10 = {
            "status": "ok",
            "review": {
                "industry_overview": "Electricity demand is increasing.",
                "market_outlook": "Data-center load supports power demand.",
                "growth_drivers": ["Data-center demand supports electricity growth."],
                "competitive_dynamics": ["Competing generation capacity remains relevant."],
                "industry_risks": ["Approval timelines can delay deployment."],
                "company_implications": ["Commercialization depends on regulatory progress."],
            },
            "sources": [],
        }
        financials = {"income": {"revenue": [0.0], "revenue_stage": "pre_revenue"}}
        call_order = []

        class ProviderTicker:
            @property
            def info(self):
                return info

        with patch("builtins.input", side_effect=[ticker_symbol, "quit"]), patch(
            "builtins.print"
        ), patch("investment_research.main.display.print_welcome"), patch(
            "investment_research.main.fetcher.yf.Ticker", return_value=ProviderTicker()
        ), ExitStack() as stack:
            for name in (
                "print_stock_info", "print_company_overview", "print_income_statement",
                "print_balance_sheet", "print_cash_flow", "print_ratios",
                "print_peer_comparison", "print_performance",
                "print_analyst_expectations", "print_news", "print_ai_analysis",
                "print_market_review", "print_bull_bear_analysis", "print_stock_assessment",
            ):
                stack.enter_context(patch(f"investment_research.main.display.{name}"))
            stack.enter_context(patch(
                "investment_research.main.financials.get_financial_statements",
                return_value=financials,
            ))
            stack.enter_context(patch(
                "investment_research.main.financials.get_ratios", return_value={}
            ))
            stack.enter_context(patch(
                "investment_research.main.peers.fetch_peer_comparison",
                return_value={"available": False},
            ))
            stack.enter_context(patch(
                "investment_research.main.performance.get_performance", return_value={}
            ))
            stack.enter_context(patch(
                "investment_research.main.expectations.get_analyst_expectations",
                return_value={},
            ))
            stack.enter_context(patch(
                "investment_research.main.news.get_company_news",
                return_value={"status": "unavailable", "articles": []},
            ))
            stack.enter_context(patch(
                "investment_research.main.analysis.get_ai_analysis",
                side_effect=lambda context: (call_order.append("feature9"), feature9)[1],
            ))
            stack.enter_context(patch(
                "investment_research.main.market_research.get_market_review",
                side_effect=lambda context: (call_order.append("feature10"), feature10)[1],
            ))
            stack.enter_context(patch(
                "investment_research.main.analysis.get_bull_bear_analysis",
                return_value={"status": "unavailable", "analysis": None},
            ))
            assessment_call = stack.enter_context(patch(
                "investment_research.main.assessment.build_stock_assessment",
                side_effect=lambda context: (
                    call_order.append("feature12"),
                    {"status": "ok", "indicators": {}},
                )[1],
            ))
            with patch("investment_research.main.display.print_error") as print_error:
                main.run()

        print_error.assert_not_called()
        self.assertEqual(call_order, ["feature9", "feature10", "feature12"])
        assessment_context = assessment_call.call_args.args[0]
        self.assertIs(assessment_context["company_analysis"], feature9)
        self.assertIs(assessment_context["market_review"], feature10)
        return assessment_context

    def test_valid_normal_pre_revenue_and_sparse_companies_continue(self):
        cases = (
            ("AAPL", {
                "symbol": "AAPL", "longName": "Apple Inc.", "quoteType": "EQUITY",
                "exchange": "NMS",
            }),
            ("OKLO", {
                "symbol": "OKLO", "longName": "Oklo Inc.", "quoteType": "EQUITY",
                "exchange": "NMS", "totalRevenue": 0, "netIncomeToCommon": -1,
            }),
            ("SPARSE", {
                "symbol": "SPARSE", "longName": "Sparse Public Company",
                "quoteType": "EQUITY", "exchange": "NMS",
            }),
        )
        for ticker, info in cases:
            with self.subTest(ticker=ticker):
                context = self._run_valid_ticker(ticker, info)
                self.assertEqual(context["company"]["ticker"], ticker)

    def test_existing_feature9_and10_evidence_makes_all_12b_indicators_eligible(self):
        context = self._run_valid_ticker(
            "OKLO",
            {"symbol": "OKLO", "longName": "Oklo Inc.", "quoteType": "EQUITY", "exchange": "NMS"},
        )
        qualitative_inputs = []
        indicators = {
            "risk": {
                "label": "Medium",
                "drivers": ["Deployment remains an execution risk.", "Regulatory reviews affect timing."],
                "evidence": ["Feature 9 identifies approval timing.", "Feature 10 notes deployment delays."],
            },
            "market_environment": {
                "label": "Favourable",
                "drivers": ["Data-center demand supports power needs.", "Demand growth supports the market."],
                "evidence": ["Feature 10 describes electricity demand.", "The review cites data-center loads."],
            },
            "competitive_position": {
                "label": "Moderate",
                "drivers": ["Competitive capacity remains a constraint.", "Peer evidence adds operating context."],
                "evidence": ["Feature 9 includes peer positioning.", "Feature 10 describes competing capacity."],
            },
        }
        with patch(
            "investment_research.assessment.gemini_provider.generate_qualitative_assessment",
            side_effect=lambda qualitative_context, **kwargs: (
                qualitative_inputs.append(qualitative_context),
                {"status": "ok", "indicators": indicators},
            )[1],
        ):
            result = assessment.build_stock_assessment(context)

        self.assertEqual(len(qualitative_inputs), 1)
        qualitative_context = qualitative_inputs[0]
        for indicator in ("risk", "market_environment", "competitive_position"):
            self.assertTrue(
                assessment._qualitative_evidence_available(qualitative_context, indicator)
            )
            self.assertNotEqual(result["indicators"][indicator]["label"], "N/A")
        self.assertEqual(result["indicators"]["growth"]["label"], "N/A")
        self.assertEqual(result["indicators"]["valuation"]["label"], "N/A")
        expected_12a = {
            "valuation": assessment.assess_valuation(context),
            "financial_quality": assessment.assess_financial_quality(context),
            "growth": assessment.assess_growth(context),
            "volatility": assessment.assess_volatility(context),
            "expectations": assessment.assess_expectations(context),
        }
        for key, expected in expected_12a.items():
            self.assertEqual(result["indicators"][key], expected)


    def test_generated_peer_symbols_are_rejected_before_provider_lookup(self):
        self.assertIsNone(peers._normalise_ticker("not a ticker"))
        self.assertEqual(peers._normalise_ticker("BRK.B"), "BRK.B")
        self.assertEqual(peers._normalise_ticker("SHOP.TO"), "SHOP.TO")


if __name__ == "__main__":
    unittest.main()
