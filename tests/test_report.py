import unittest
from unittest.mock import patch

from investment_research import main


class StructuredReportTests(unittest.TestCase):
    def _patch_pipeline(self, stack, *, market=None, bull_bear=None, assessment_result=None):
        company = {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "price": 225.0,
            "market_cap": 3_000_000_000_000,
            "exchange": "NMS",
            "market": "us_market",
        }
        statements = {"income": {"revenue_stage": "operating"}}
        ratios = {"valuation": {"trailing_pe": 30.0}}
        peers = {"available": True, "tickers": ["AAPL", "MSFT"]}
        price_performance = {"available": True, "returns": {}}
        expectations = {"status": "ok"}
        news_result = {"status": "unavailable", "articles": []}
        company_analysis = {"status": "ok", "analysis": {"peer_positioning": "Leads peers."}}
        market_review = market or {"status": "ok", "review": {"industry_overview": "Demand is stable."}, "sources": []}
        bull_bear_result = bull_bear or {"status": "ok", "analysis": {"bull_case": [], "bear_case": [], "swing_factors": []}}
        stock_assessment = assessment_result or {"status": "ok", "indicators": {}}

        stack.enter_context(patch("investment_research.main.fetcher.get_stock_info", return_value=company))
        stack.enter_context(patch("investment_research.main.financials.get_financial_statements", return_value=statements))
        stack.enter_context(patch("investment_research.main.financials.get_ratios", return_value=ratios))
        stack.enter_context(patch("investment_research.main.peers.fetch_peer_comparison", return_value=peers))
        stack.enter_context(patch("investment_research.main.performance.get_performance", return_value=price_performance))
        stack.enter_context(patch("investment_research.main.expectations.get_analyst_expectations", return_value=expectations))
        stack.enter_context(patch("investment_research.main.news.get_company_news", return_value=news_result))
        stack.enter_context(patch("investment_research.main.analysis.get_ai_analysis", return_value=company_analysis))
        stack.enter_context(patch("investment_research.main.market_research.get_market_review", return_value=market_review))
        stack.enter_context(patch("investment_research.main.analysis.get_bull_bear_analysis", return_value=bull_bear_result))
        assessment_call = stack.enter_context(
            patch("investment_research.main.assessment.build_stock_assessment", return_value=stock_assessment)
        )
        return company, statements, ratios, peers, price_performance, expectations, news_result, company_analysis, market_review, bull_bear_result, stock_assessment, assessment_call

    def test_valid_ticker_returns_structured_report_and_reuses_feature_outputs(self):
        from contextlib import ExitStack

        with ExitStack() as stack:
            values = self._patch_pipeline(stack)
            report = main.build_report(" aapl ")

        company, statements, ratios, peers, price_performance, expectations, news_result, company_analysis, market_review, bull_bear_result, stock_assessment, assessment_call = values
        self.assertEqual(report["ticker"], "AAPL")
        for section in (
            "company", "financials", "ratios", "peers", "price_performance",
            "expectations", "news", "company_analysis", "market_review",
            "bull_bear", "assessment",
        ):
            self.assertIn(section, report)
        self.assertIs(report["company"], company)
        self.assertIs(report["financials"], statements)
        self.assertIs(report["ratios"], ratios)
        self.assertIs(report["peers"], peers)
        self.assertIs(report["price_performance"], price_performance)
        self.assertIs(report["expectations"], expectations)
        self.assertIs(report["news"], news_result)
        self.assertIs(report["company_analysis"], company_analysis)
        self.assertIs(report["market_review"], market_review)
        self.assertIs(report["bull_bear"], bull_bear_result)
        self.assertIs(report["assessment"], stock_assessment)
        assessment_context = assessment_call.call_args.args[0]
        self.assertIs(assessment_context["company_analysis"], company_analysis)
        self.assertIs(assessment_context["market_review"], market_review)

    def test_invalid_ticker_returns_none_without_running_later_features(self):
        with patch("investment_research.main.fetcher.get_stock_info", return_value=None), patch(
            "investment_research.main.financials.get_financial_statements"
        ) as statements, patch(
            "investment_research.main.market_research.get_market_review"
        ) as market:
            report = main.build_report("NOPE")

        self.assertIsNone(report)
        statements.assert_not_called()
        market.assert_not_called()

    def test_optional_feature_failures_do_not_prevent_report_creation(self):
        from contextlib import ExitStack

        with ExitStack() as stack:
            values = self._patch_pipeline(
                stack,
                bull_bear={"status": "unavailable", "analysis": None},
                assessment_result={"status": "ok", "indicators": {
                    "risk": {"label": "N/A"},
                }},
            )
            stack.enter_context(
                patch(
                    "investment_research.main.market_research.get_market_review",
                    side_effect=RuntimeError("provider down"),
                )
            )
            stack.enter_context(
                patch(
                    "investment_research.main.analysis.get_bull_bear_analysis",
                    side_effect=RuntimeError("provider down"),
                )
            )
            stack.enter_context(
                patch(
                    "investment_research.main.assessment.build_stock_assessment",
                    side_effect=RuntimeError("provider down"),
                )
            )
            report = main.build_report("AAPL")

        self.assertIsNotNone(report)
        self.assertEqual(report["market_review"]["status"], "unavailable")
        self.assertEqual(report["bull_bear"]["status"], "unavailable")
        self.assertEqual(report["assessment"]["indicators"], {})
        self.assertIn("assessment", report["errors"])

    def test_terminal_loop_uses_shared_report_and_existing_renderer(self):
        report = {"ticker": "AAPL", "company": {}}
        with patch("investment_research.main.display.print_welcome"), patch(
            "builtins.input", side_effect=["AAPL", "quit"]
        ), patch("builtins.print"), patch(
            "investment_research.main.build_report", return_value=report
        ) as build, patch(
            "investment_research.main.render_terminal_report"
        ) as render:
            main.run()

        build.assert_called_once_with("AAPL")
        render.assert_called_once_with(report)

