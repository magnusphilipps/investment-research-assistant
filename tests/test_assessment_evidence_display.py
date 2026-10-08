import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from investment_research.assessment_display import (
    ASSESSMENT_INDICATORS,
    get_assessment_display,
    get_indicator_evidence_display,
)


def _report():
    return {
        "company": {"sector": "Technology", "price": 150.0},
        "assessment": {
            "indicators": {
                "valuation": {
                    "label": "Cheap",
                    "drivers": ["P/E trades below the peer median."],
                    "score": 8.5,
                },
                "financial_quality": {"label": "Strong", "drivers": ["Margins are resilient."]},
                "growth": {"label": "Strong", "drivers": ["Revenue is growing."]},
                "risk": {"label": "Moderate", "drivers": ["Leverage is manageable."]},
                "volatility": {
                    "label": "High",
                    "drivers": ["Annualized volatility is elevated."],
                    "components": {
                        "annualized_volatility": {"value": 0.472, "score": 2},
                        "beta": {"value": 1.8, "score": 2},
                        "max_drawdown": {"value": 0.31, "score": 2},
                    },
                    "score": 6,
                },
                "market_environment": {"label": "Moderate", "drivers": ["Conditions are mixed."]},
                "competitive_position": {"label": "Strong", "drivers": ["Peer positioning is strong."]},
                "expectations": {"label": "Moderate", "drivers": ["Estimates are mixed."]},
            }
        },
        "ratios": {
            "valuation": {
                "trailing_pe": 20.5,
                "trailing_pe_status": "available",
                "forward_pe": 18.2,
                "forward_pe_status": "available",
                "peg": None,
                "peg_status": "not_meaningful",
                "ev_ebitda": 12.1,
                "pb": 3.4,
            },
            "profitability": {
                "net_margin": 12.5,
                "op_margin": 18.2,
                "roe": 16.0,
                "roa": 8.0,
            },
            "strength": {
                "de_ratio": 0.4,
                "current_ratio": 1.8,
                "cash_to_debt": 1.2,
            },
        },
        "financials": {
            "income": {
                "years": [2025, 2024],
                "revenue": [100_000_000, 80_000_000],
                "revenue_status": ["available", "available"],
                "revenue_growth": [25.0, None],
                "revenue_growth_status": ["available", "not_meaningful"],
                "revenue_stage": "operating",
                "acceleration": "Accelerating",
                "op_margin": [18.2, 15.0],
                "op_margin_status": ["available", "available"],
            },
            "cashflow": {"operating_cf": 12_000_000, "free_cash_flow": 8_000_000},
            "balance": {},
        },
        "expectations": {
            "price_targets": {
                "current_price": 150.0,
                "average_target": 180.0,
                "median_target": 175.0,
                "high_target": 220.0,
                "low_target": 130.0,
                "implied_upside": 0.2,
                "analysts": 12,
            },
            "recommendations": {
                "consensus": "Buy",
                "counts": {"Strong Buy": 3, "Buy": 5, "Hold": 2, "Sell": 1, "Strong Sell": 1},
            },
            "revenue_estimates": {
                "current_year": {"revenue": 110_000_000, "growth": 0.1, "growth_status": "available"},
                "next_year": {"revenue": 130_000_000, "growth": None, "growth_status": "not_meaningful"},
            },
        },
        "price_performance": {
            "returns": {"1 Month": 0.05, "6 Months": 0.12, "1 Year": 0.2},
            "daily_returns": [0.01] * 400,
            "annualized_volatility": 0.472,
            "beta": 1.8,
            "max_drawdown": -0.31,
            "range": {"current_price": 150.0, "high": 200.0, "low": 100.0},
        },
        "company_analysis": {
            "status": "ok",
            "analysis": {
                "key_factors_to_watch": ["Monitor cash burn."],
                "peer_positioning": "The company is gaining share.",
            },
        },
        "market_review": {
            "status": "ok",
            "review": {
                "market_outlook": "Demand is growing.",
                "growth_drivers": ["Adoption is expanding."],
                "industry_risks": ["Input costs may rise."],
                "company_implications": ["Capacity investment may be needed."],
                "regulatory_environment": "Regulatory review is ongoing.",
                "macro_exposure": "Rates may affect demand.",
                "competitive_dynamics": ["Competition remains active."],
            },
        },
        "bull_bear": {
            "status": "ok",
            "analysis": {"bear_case": ["Margins could contract."]},
        },
        "peers": {
            "available": True,
            "tickers": ["ABC", "PEER1", "PEER2"],
            "df": pd.DataFrame(
                {
                    "ABC": [20.5, 18.2, 12.1, 25.0, 18.2, 16.0, 0.4],
                    "PEER1": [22.0, 19.0, 13.0, 15.0, 16.0, 14.0, 0.8],
                    "PEER2": [18.0, 16.0, 11.0, 20.0, 12.0, 10.0, 1.1],
                },
                index=[
                    "P/E", "Forward P/E", "EV/EBITDA", "Revenue Growth",
                    "Operating Margin", "ROE", "Debt/Equity",
                ],
            ),
        },
    }


class AssessmentEvidenceDisplayTests(unittest.TestCase):
    def test_evidence_is_structured_as_display_ready_values(self):
        evidence = get_indicator_evidence_display(_report(), "valuation", "Valuation")

        self.assertEqual(
            set(evidence),
            {"name", "metrics", "tables", "bullets", "paragraphs", "available"},
        )
        self.assertEqual(evidence["name"], "Valuation")
        self.assertTrue(evidence["available"])
        self.assertTrue(all(isinstance(metric["value"], str) for metric in evidence["metrics"]))
        self.assertNotIn("daily_returns", str(evidence))
        self.assertNotIn("score", str(evidence))

    def test_valuation_selects_only_valuation_metrics_and_peer_values(self):
        evidence = get_indicator_evidence_display(_report(), "valuation", "Valuation")

        self.assertEqual(
            [metric["label"] for metric in evidence["metrics"]],
            [
                "Trailing P/E", "Forward P/E", "PEG", "EV / EBITDA",
                "Price / Book", "EV / Revenue", "Price / Sales",
            ],
        )
        values = {metric["label"]: metric["value"] for metric in evidence["metrics"]}
        self.assertEqual(values["PEG"], "N/M")
        self.assertEqual(values["Trailing P/E"], "20.50x")
        self.assertEqual(evidence["tables"][0]["columns"], ["Metric", "ABC", "PEER1", "PEER2"])
        self.assertNotIn("daily_returns", str(evidence))

    def test_financial_quality_has_grouped_readable_metrics(self):
        evidence = get_indicator_evidence_display(_report(), "financial_quality", "Financial Quality")

        metrics = {metric["label"]: metric for metric in evidence["metrics"]}
        self.assertEqual(metrics["Net Margin"]["value"], "12.5%")
        self.assertEqual(metrics["ROE"]["group"], "Profitability")
        self.assertEqual(metrics["Operating Cash Flow"]["value"], "$12,000,000")
        self.assertEqual(metrics["Debt / Equity"]["value"], "0.40")
        self.assertNotIn("'years':", str(evidence))
        self.assertNotIn("'cashflow':", str(evidence))

    def test_financial_sector_omits_industrial_balance_sheet_ratios(self):
        report = _report()
        report["company"]["sector"] = "Financial Services"

        evidence = get_indicator_evidence_display(report, "financial_quality", "Financial Quality")

        labels = {metric["label"] for metric in evidence["metrics"]}
        self.assertNotIn("Debt / Equity", labels)
        self.assertNotIn("Current Ratio", labels)
        self.assertNotIn("Cash / Debt", labels)

    def test_growth_has_historical_table_and_preserves_pre_revenue_nm(self):
        report = _report()
        report["financials"]["income"]["revenue_stage"] = "pre_revenue"
        report["financials"]["income"]["revenue_status"] = ["not_meaningful", "not_meaningful"]
        report["financials"]["income"]["revenue_growth_status"] = ["not_meaningful", "not_meaningful"]
        report["expectations"]["revenue_estimates"]["next_year"]["growth_status"] = "not_meaningful"

        evidence = get_indicator_evidence_display(report, "growth", "Growth")

        historical = evidence["tables"][0]
        self.assertEqual(historical["title"], "Historical revenue")
        self.assertEqual(historical["rows"][0]["Year"], "2025")
        self.assertEqual(historical["rows"][0]["Revenue"], "N/M")
        self.assertEqual(historical["rows"][0]["Revenue Growth"], "N/M")
        metrics = {metric["label"]: metric["value"] for metric in evidence["metrics"]}
        self.assertEqual(metrics["Revenue Stage"], "Pre-revenue")
        self.assertEqual(evidence["tables"][1]["rows"][1]["Expected Growth"], "N/M")

    def test_volatility_exposes_only_summary_metrics_not_daily_returns(self):
        evidence = get_indicator_evidence_display(_report(), "volatility", "Volatility")

        metrics = {metric["label"]: metric["value"] for metric in evidence["metrics"]}
        self.assertEqual(metrics["Annualized Volatility"], "47.2%")
        self.assertEqual(metrics["Beta"], "1.80")
        self.assertEqual(metrics["Max Drawdown"], "31.0%")
        self.assertEqual(metrics["1 Month Return"], "5.0%")
        self.assertEqual(metrics["52-week High"], "$200.00")
        self.assertNotIn("daily_returns", str(evidence))
        self.assertNotIn("400", str(evidence))

    def test_risk_market_and_competitive_evidence_are_narrative_and_peer_ordered(self):
        report = _report()
        risk = get_indicator_evidence_display(report, "risk", "Risk")
        market = get_indicator_evidence_display(report, "market_environment", "Market Environment")
        competitive = get_indicator_evidence_display(report, "competitive_position", "Competitive Position")

        self.assertEqual(risk["bullets"][0]["items"], ["Monitor cash burn."])
        self.assertEqual(market["paragraphs"][0]["text"], "Demand is growing.")
        peer_table = competitive["tables"][0]
        self.assertEqual(peer_table["columns"], ["Metric", "ABC", "PEER1", "PEER2"])
        self.assertEqual(peer_table["rows"][0]["Metric"], "Revenue Growth")
        self.assertEqual(competitive["paragraphs"][0]["title"], "Peer Positioning")

    def test_expectations_are_formatted_and_consensus_is_factual(self):
        evidence = get_indicator_evidence_display(_report(), "expectations", "Expectations")

        metrics = {metric["label"]: metric["value"] for metric in evidence["metrics"]}
        self.assertEqual(metrics["Average Target"], "$180.00")
        self.assertEqual(metrics["Implied Upside"], "20.0%")
        self.assertEqual(metrics["Analyst Count"], "12")
        self.assertEqual(metrics["Consensus"], "Buy")
        self.assertEqual(evidence["tables"][0]["rows"][1]["Expected Growth"], "N/M")

    def test_missing_values_remain_na_and_hidden_scores_stay_hidden(self):
        report = _report()
        cards = get_assessment_display(report)
        evidence = get_indicator_evidence_display(report, "valuation", "Valuation")

        self.assertEqual(len(cards), len(ASSESSMENT_INDICATORS))
        self.assertNotIn("score", str(cards))
        self.assertNotIn("score", str(evidence))
        self.assertIn("N/A", {metric["value"] for metric in evidence["metrics"]})

    def test_original_cards_offer_evidence_buttons_without_separate_tabs(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app_source = app_path.read_text(encoding="utf-8")

        self.assertIn('"View evidence"', app_source)
        self.assertIn('key=f"assessment-evidence-{indicator_key}"', app_source)
        self.assertIn('with st.container(border=True):', app_source)
        self.assertNotIn("st.tabs(", app_source)
        self.assertNotIn('st.subheader("Assessment Evidence")', app_source)
        self.assertNotIn('with st.expander("Supporting evidence"', app_source)

    def test_evidence_extraction_does_not_call_providers_or_build_report(self):
        report = _report()
        with (
            patch("investment_research.main.build_report") as build_report,
            patch("investment_research.gemini_provider.generate_qualitative_assessment") as gemini,
            patch("investment_research.analysis.get_ai_analysis") as analysis,
            patch("investment_research.market_research.get_market_review") as market,
        ):
            for key, name in ASSESSMENT_INDICATORS:
                get_indicator_evidence_display(report, key, name)

        build_report.assert_not_called()
        gemini.assert_not_called()
        analysis.assert_not_called()
        market.assert_not_called()


if __name__ == "__main__":
    unittest.main()
