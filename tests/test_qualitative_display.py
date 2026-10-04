import copy
import runpy
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from investment_research import qualitative_display


class QualitativeDisplayTests(unittest.TestCase):
    def test_company_analysis_sections_use_existing_feature_nine_data(self):
        report = {
            "company_analysis": {
                "status": "ok",
                "analysis": {
                    "financial_performance": "Revenue grew.",
                    "financial_position": "Cash remains available.",
                    "valuation": "The multiple is elevated.",
                    "share_price_and_expectations": "Expectations are mixed.",
                    "peer_positioning": "Peer positioning is stable.",
                    "recent_developments": "A product was launched.",
                    "key_factors_to_watch": ["Watch margins.", "Monitor cash flow."],
                    "hidden_internal": "Do not display this.",
                },
            }
        }

        result = qualitative_display.get_company_analysis_display(report)

        self.assertTrue(result["available"])
        self.assertEqual([item["title"] for item in result["sections"]], [
            "Financial Performance",
            "Financial Position",
            "Valuation",
            "Share Price & Expectations",
            "Peer Positioning",
            "Recent Developments",
            "Key Factors to Watch",
        ])
        self.assertEqual(result["sections"][0]["content"], "Revenue grew.")
        self.assertEqual(result["sections"][-1]["content"], [
            "Watch margins.",
            "Monitor cash flow.",
        ])
        self.assertNotIn("hidden_internal", str(result))
        self.assertNotIn("Do not display this.", str(result))

    def test_missing_company_analysis_subsection_is_omitted(self):
        result = qualitative_display.get_company_analysis_display({
            "company_analysis": {
                "status": "ok",
                "analysis": {
                    "financial_performance": "  ",
                    "valuation": None,
                    "key_factors_to_watch": [],
                },
            }
        })

        self.assertTrue(result["available"])
        self.assertEqual(result["sections"], [])

    def test_narrative_sanitization_preserves_figures_prose_and_paragraphs(self):
        original_text = (
            "Revenue was $529.8 million. The `net margin` improved.\n\n"
            "Ordinary prose stays exactly as written."
        )
        report = {
            "company_analysis": {
                "status": "ok",
                "analysis": {"financial_performance": original_text},
            },
            "market_review": {
                "status": "ok",
                "review": {
                    "industry_overview": "Costs reached `$12.4 million`.\nSecond paragraph.",
                },
            },
            "bull_bear": {
                "status": "ok",
                "analysis": {
                    "bull_case": ["Demand may add `$5 million`."],
                },
            },
        }
        original_report = copy.deepcopy(report)

        company = qualitative_display.get_company_analysis_display(report)
        market = qualitative_display.get_market_review_display(report)
        bull_bear = qualitative_display.get_bull_bear_display(report)

        self.assertEqual(
            company["sections"][0]["content"],
            "Revenue was \\$529.8 million. The net margin improved.\n\n"
            "Ordinary prose stays exactly as written.",
        )
        self.assertEqual(
            market["sections"][0]["content"],
            "Costs reached \\$12.4 million.\nSecond paragraph.",
        )
        self.assertEqual(
            bull_bear["sections"][0]["content"],
            ["Demand may add \\$5 million."],
        )
        self.assertEqual(report, original_report)

    def test_market_review_narratives_bullets_and_compact_sources(self):
        result = qualitative_display.get_market_review_display({
            "market_review": {
                "status": "ok",
                "review": {
                    "industry_overview": "Demand is growing. (S1)",
                    "market_outlook": "Outlook remains mixed https://example.com/report",
                    "growth_drivers": ["Adoption may expand. (S1)", " ", None],
                    "competitive_dynamics": ["Competition is active."],
                    "industry_risks": ["Costs may rise."],
                    "company_implications": ["Capacity could matter."],
                    "sources_used": ["S1"],
                    "backend_only": "Do not display this.",
                },
                "sources": [
                    {
                        "id": "S1",
                        "title": "Industry outlook",
                        "source": "example.com",
                        "published_at": "2026-09-30",
                        "url": "https://example.com/report",
                        "content": "Internal source content.",
                        "relevance_score": 0.98,
                        "cache_key": "internal",
                    }
                ],
                "cache_metadata": {"key": "internal"},
            }
        })

        self.assertTrue(result["available"])
        self.assertEqual(
            [(item["title"], item["kind"]) for item in result["sections"]],
            [
                ("Industry Overview", "text"),
                ("Market Outlook", "text"),
                ("Growth Drivers", "list"),
                ("Competitive Dynamics", "list"),
                ("Industry Risks", "list"),
                ("Implications for the Company", "list"),
            ],
        )
        self.assertEqual(result["sections"][0]["content"], "Demand is growing.")
        self.assertEqual(result["sections"][1]["content"], "Outlook remains mixed")
        self.assertEqual(result["sections"][2]["content"], ["Adoption may expand."])
        self.assertEqual(result["sources"], [{
            "title": "Industry outlook",
            "source": "example.com",
            "published_at": "2026-09-30",
            "url": "https://example.com/report",
        }])
        self.assertNotIn("backend_only", str(result))
        self.assertNotIn("Internal source content.", str(result))
        self.assertNotIn("relevance_score", str(result))
        self.assertNotIn("cache_key", str(result))
        self.assertNotIn("S1", str(result))

    def test_market_sources_exclude_low_value_and_select_at_most_three_deterministically(self):
        report = {
            "company": {"website": "https://acme.example"},
            "market_review": {
                "status": "ok",
                "review": {},
                "sources": [
                    {
                        "title": "Company market outlook",
                        "source": "News publisher",
                        "url": "https://news.example/story",
                    },
                    {
                        "title": "LinkedIn company update",
                        "source": "LinkedIn",
                        "url": "https://www.linkedin.com/posts/acme",
                    },
                    {
                        "title": "Industry market review",
                        "source": "Research journal",
                        "url": "https://journal.example/research",
                    },
                    {
                        "title": "Wikipedia industry page",
                        "source": "Wikipedia",
                        "url": "https://en.wikipedia.org/wiki/Industry",
                    },
                    {
                        "title": "Acme",
                        "source": "Acme",
                        "url": "https://acme.example/",
                    },
                    {
                        "title": "About Us",
                        "source": "Acme",
                        "url": "https://acme.example/about-us",
                    },
                    {
                        "title": "Analysis of market demand",
                        "source": "Editorial desk",
                        "published_at": "2026-10-01",
                        "url": "https://editorial.example/analysis",
                    },
                    {
                        "title": "Background note",
                        "source": "General reference",
                        "url": "https://reference.example/background",
                    },
                ],
            },
        }
        original_report = copy.deepcopy(report)

        sources = qualitative_display.get_market_review_display(report)["sources"]

        self.assertEqual(len(sources), 3)
        self.assertEqual(
            [source["title"] for source in sources],
            [
                "Industry market review",
                "Company market outlook",
                "Analysis of market demand",
            ],
        )
        self.assertTrue(all(source["url"].startswith("https://") for source in sources))
        self.assertEqual(report, original_report)
        self.assertEqual(
            sources,
            qualitative_display.get_market_review_display(report)["sources"],
        )

    def test_fewer_than_three_suitable_sources_are_not_filled_with_low_value_sources(self):
        report = {
            "company": {"website": "https://acme.example"},
            "market_review": {
                "status": "ok",
                "review": {},
                "sources": [
                    {
                        "title": "Useful industry report",
                        "source": "Research desk",
                        "url": "https://research.example/report",
                    },
                    {
                        "title": "LinkedIn company page",
                        "source": "LinkedIn",
                        "url": "https://linkedin.com/company/acme",
                    },
                    {
                        "title": "About",
                        "source": "Acme",
                        "url": "https://acme.example/about",
                    },
                ],
            },
        }

        sources = qualitative_display.get_market_review_display(report)["sources"]

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["title"], "Useful industry report")

    def test_malformed_market_source_url_is_not_rendered_as_a_link(self):
        result = qualitative_display.get_market_review_display({
            "market_review": {
                "status": "ok",
                "review": {},
                "sources": [{
                    "title": "Industry report",
                    "source": "Research desk",
                    "published_at": "2026-09-30",
                    "url": "javascript:alert(1)",
                }],
            },
        })

        self.assertEqual(result["sources"], [{
            "title": "Industry report",
            "source": "Research desk",
            "published_at": "2026-09-30",
            "url": None,
        }])

    def test_unavailable_market_review_uses_backend_message_or_fallback(self):
        report = {"market_review": {
            "status": "unavailable",
            "message": "Market research is temporarily unavailable.",
            "review": None,
            "sources": [],
        }}

        self.assertEqual(
            qualitative_display.get_market_review_display(report),
            {
                "available": False,
                "message": "Market research is temporarily unavailable.",
                "sections": [],
                "sources": [],
            },
        )
        self.assertIn(
            "Market & industry review temporarily unavailable.",
            qualitative_display.get_market_review_display({})["message"],
        )

    def test_bull_bear_scenario_sections_use_feature_eleven_data(self):
        result = qualitative_display.get_bull_bear_display({
            "bull_bear": {
                "status": "ok",
                "analysis": {
                    "bull_case": ["Existing bull case."],
                    "bear_case": ["Existing bear case."],
                    "swing_factors": ["Existing swing factor."],
                    "internal_score": 0.5,
                },
            }
        })

        self.assertEqual(
            result["sections"],
            [
                {"title": "Bull Case", "kind": "list", "content": ["Existing bull case."]},
                {"title": "Bear Case", "kind": "list", "content": ["Existing bear case."]},
                {
                    "title": "Key Swing Factors",
                    "kind": "list",
                    "content": ["Existing swing factor."],
                },
            ],
        )
        self.assertNotIn("internal_score", str(result))

    def test_unavailable_bull_bear_uses_backend_message_or_fallback(self):
        report = {"bull_bear": {
            "status": "unavailable",
            "message": "Bull / Bear analysis temporarily unavailable.",
            "analysis": None,
        }}

        result = qualitative_display.get_bull_bear_display(report)

        self.assertFalse(result["available"])
        self.assertEqual(result["message"], "Bull / Bear analysis temporarily unavailable.")
        self.assertEqual(result["sections"], [])
        self.assertEqual(
            qualitative_display.get_bull_bear_display({})["message"],
            "Bull / Bear analysis temporarily unavailable.",
        )

    def test_list_fields_filter_blank_and_non_string_items_without_reordering(self):
        result = qualitative_display.get_bull_bear_display({
            "bull_bear": {
                "status": "ok",
                "analysis": {
                    "bull_case": ["First", None, " ", 4, "Last"],
                    "bear_case": None,
                    "swing_factors": [" Factor ", False],
                },
            }
        })

        self.assertEqual(result["sections"], [
            {"title": "Bull Case", "kind": "list", "content": ["First", "Last"]},
            {"title": "Key Swing Factors", "kind": "list", "content": ["Factor"]},
        ])

    def test_display_extraction_does_not_call_backend_providers(self):
        report = {
            "company_analysis": {"status": "ok", "analysis": {}},
            "market_review": {"status": "ok", "review": {}, "sources": []},
            "bull_bear": {"status": "ok", "analysis": {}},
        }
        with patch("investment_research.gemini_provider.generate_analysis") as company_provider, patch(
            "investment_research.gemini_provider.generate_market_review"
        ) as market_provider, patch(
            "investment_research.gemini_provider.generate_bull_bear"
        ) as scenario_provider, patch("investment_research.tavily_provider.search") as search:
            qualitative_display.get_company_analysis_display(report)
            qualitative_display.get_market_review_display(report)
            qualitative_display.get_bull_bear_display(report)

        company_provider.assert_not_called()
        market_provider.assert_not_called()
        scenario_provider.assert_not_called()
        search.assert_not_called()

    def test_streamlit_renders_collapsed_sections_from_saved_report_only(self):
        saved_report = {
            "ticker": "AAPL",
            "company": {"name": "Apple Inc.", "price": 200, "market_cap": 1_000_000},
            "assessment": {"indicators": {}},
            "company_analysis": {
                "status": "ok",
                "analysis": {"financial_performance": "Stored company analysis."},
            },
            "market_review": {
                "status": "ok",
                "review": {"industry_overview": "Stored market review."},
                "sources": [{
                    "title": "Stored source",
                    "source": "Research desk",
                    "url": "https://research.example/report",
                }],
            },
            "bull_bear": {
                "status": "ok",
                "analysis": {"bull_case": ["Stored scenario analysis."]},
            },
        }
        fake_streamlit = _FakeStreamlit(saved_report)
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.main.build_report"
        ) as build_report, patch(
            "investment_research.gemini_provider.generate_analysis"
        ) as company_provider, patch(
            "investment_research.gemini_provider.generate_market_review"
        ) as market_provider, patch(
            "investment_research.gemini_provider.generate_bull_bear"
        ) as scenario_provider, patch("investment_research.tavily_provider.search") as search:
            runpy.run_path(str(app_path), run_name="feature_13c_app_test")

        self.assertEqual(fake_streamlit.expanders, [
            ("AI Company Analysis", {"expanded": False}),
            ("Market & Industry Review", {"expanded": False}),
            ("Bull / Bear Scenario Analysis", {"expanded": False}),
        ])
        rendered = "\n".join(fake_streamlit.markdown_calls + fake_streamlit.write_calls)
        self.assertIn("Stored company analysis.", rendered)
        self.assertIn("Stored market review.", rendered)
        self.assertIn("Stored scenario analysis.", rendered)
        self.assertIn("[Stored source](https://research.example/report)", rendered)
        build_report.assert_not_called()
        company_provider.assert_not_called()
        market_provider.assert_not_called()
        scenario_provider.assert_not_called()
        search.assert_not_called()

    def test_unavailable_market_section_does_not_hide_other_sections(self):
        fake_streamlit = _FakeStreamlit({
            "ticker": "AAPL",
            "company": {"name": "Apple Inc.", "price": 200, "market_cap": 1_000_000},
            "assessment": {"indicators": {}},
            "company_analysis": {
                "status": "ok",
                "analysis": {"financial_performance": "Company content remains visible."},
            },
            "market_review": {
                "status": "unavailable",
                "message": "Market review is temporarily unavailable.",
                "review": None,
                "sources": [],
            },
            "bull_bear": {
                "status": "ok",
                "analysis": {"bull_case": ["Scenario content remains visible."]},
            },
        })
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.main.build_report"
        ) as build_report:
            runpy.run_path(str(app_path), run_name="feature_13c_unavailable_market_test")

        rendered = "\n".join(
            fake_streamlit.markdown_calls
            + fake_streamlit.write_calls
            + fake_streamlit.info_calls
        )
        self.assertIn("Company content remains visible.", rendered)
        self.assertIn("Market review is temporarily unavailable.", rendered)
        self.assertIn("Scenario content remains visible.", rendered)
        build_report.assert_not_called()


class _FakeColumn:
    def metric(self, *_args, **_kwargs):
        return None

    def container(self, **_kwargs):
        return nullcontext()


class _FakeStreamlit:
    def __init__(self, saved_report):
        self.session_state = {"research_report": saved_report}
        self.expanders = []
        self.markdown_calls = []
        self.write_calls = []
        self.info_calls = []

    def set_page_config(self, **_kwargs):
        return None

    def title(self, *_args, **_kwargs):
        return None

    def write(self, value, *_args, **_kwargs):
        self.write_calls.append(str(value))

    def subheader(self, *_args, **_kwargs):
        return None

    def columns(self, count):
        return [_FakeColumn() for _ in range(count)]

    def markdown(self, value, **_kwargs):
        self.markdown_calls.append(str(value))

    def caption(self, *_args, **_kwargs):
        return None

    def info(self, value, *_args, **_kwargs):
        self.info_calls.append(str(value))

    def text_input(self, *_args, **_kwargs):
        return ""

    def form(self, *_args, **_kwargs):
        return nullcontext()

    def form_submit_button(self, *_args, **_kwargs):
        return False

    def expander(self, title, **kwargs):
        self.expanders.append((title, kwargs))
        return nullcontext()

    def spinner(self, *_args, **_kwargs):
        return nullcontext()


if __name__ == "__main__":
    unittest.main()
