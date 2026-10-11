import copy
import json
import runpy
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from investment_research import fetcher, qualitative_display, ticker_resolution
from investment_research.ticker_resolution import TickerResolution


class QualitativeDisplayTests(unittest.TestCase):
    def setUp(self):
        fetcher.clear_yahoo_info_cache()
        ticker_resolution.clear_resolution_cache()

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
        self.assertEqual(
            [key for _, key, _ in fake_streamlit.buttons],
            [
                "assessment-evidence-valuation",
                "assessment-evidence-financial_quality",
                "assessment-evidence-growth",
                "assessment-evidence-risk",
                "assessment-evidence-volatility",
                "assessment-evidence-market_environment",
                "assessment-evidence-competitive_position",
                "assessment-evidence-expectations",
            ],
        )
        self.assertEqual(
            sum('class="assessment-card"' in markup for markup in fake_streamlit.markdown_calls),
            8,
        )
        rendered_cards = "\n".join(
            markup for markup in fake_streamlit.markdown_calls
            if 'class="assessment-card"' in markup
        )
        for indicator_name in (
            "Valuation",
            "Financial Quality",
            "Growth",
            "Risk",
            "Volatility",
            "Market Environment",
            "Competitive Position",
            "Expectations",
        ):
            self.assertIn(f'class="assessment-card-title">{indicator_name}</div>', rendered_cards)
        rendered = "\n".join(fake_streamlit.markdown_calls + fake_streamlit.write_calls)
        self.assertIn("Stored company analysis.", rendered)
        self.assertIn("Stored market review.", rendered)
        self.assertIn("Stored scenario analysis.", rendered)
        self.assertIn("[Stored source](https://research.example/report)", rendered)
        self.assertIsNone(fake_streamlit.session_state.get("selected_evidence_indicator"))
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

    def test_row_one_selection_renders_full_width_evidence_after_row_one(self):
        fake_streamlit = _FakeStreamlit(
            _dashboard_report(),
            click_button_key="assessment-evidence-valuation",
        )
        _run_app(fake_streamlit)

        events = fake_streamlit.events
        panel_index = events.index(("markdown", "### Valuation"))
        row_one_last_card_index = next(
            index for index, (kind, value) in enumerate(events)
            if kind == "markdown" and "assessment-card-title\">Risk</div>" in value
        )
        row_two_first_card_index = next(
            index for index, (kind, value) in enumerate(events)
            if kind == "markdown" and "assessment-card-title\">Volatility</div>" in value
        )
        self.assertLess(row_one_last_card_index, panel_index)
        self.assertLess(panel_index, row_two_first_card_index)
        self.assertEqual(
            fake_streamlit.session_state["selected_evidence_indicator"],
            "valuation",
        )
        self.assertEqual(fake_streamlit.tables[0][0], {"Metric": "Trailing P/E", "Value": "20.50x"})

    def test_assessment_layout_defaults_to_desktop_and_keeps_two_rows_of_four(self):
        fake_streamlit = _FakeStreamlit(_dashboard_report())
        _run_app(fake_streamlit)

        self.assertEqual(fake_streamlit.session_state["assessment_layout_mode"], "Desktop")
        self.assertEqual(fake_streamlit.segmented_controls, [
            ("Layout", ("Desktop", "Mobile"), "assessment_layout_mode"),
        ])
        self.assertEqual(fake_streamlit.column_counts, [2, 4, 4])
        self.assertEqual(
            [
                key for _, key, _ in fake_streamlit.buttons
                if key.startswith("assessment-evidence-")
            ],
            [
                "assessment-evidence-valuation",
                "assessment-evidence-financial_quality",
                "assessment-evidence-growth",
                "assessment-evidence-risk",
                "assessment-evidence-volatility",
                "assessment-evidence-market_environment",
                "assessment-evidence-competitive_position",
                "assessment-evidence-expectations",
            ],
        )

    def test_row_two_selection_renders_full_width_evidence_after_row_two(self):
        fake_streamlit = _FakeStreamlit(
            _dashboard_report(),
            click_button_key="assessment-evidence-volatility",
        )
        _run_app(fake_streamlit)

        events = fake_streamlit.events
        last_row_card_index = next(
            index for index, (kind, value) in enumerate(events)
            if kind == "markdown" and "assessment-card-title\">Expectations</div>" in value
        )
        panel_index = events.index(("markdown", "### Volatility"))
        self.assertLess(last_row_card_index, panel_index)
        self.assertEqual(
            fake_streamlit.session_state["selected_evidence_indicator"],
            "volatility",
        )
        self.assertNotIn("daily_returns", str(fake_streamlit.tables))

    def test_mobile_mode_renders_all_indicators_sequentially_with_evidence_in_place(self):
        fake_streamlit = _FakeStreamlit(
            _dashboard_report(),
            selected_indicator="growth",
            layout_mode="Mobile",
        )
        _run_app(fake_streamlit)

        card_names = (
            "Valuation",
            "Financial Quality",
            "Growth",
            "Risk",
            "Volatility",
            "Market Environment",
            "Competitive Position",
            "Expectations",
        )
        card_positions = [
            next(
                index for index, (kind, value) in enumerate(fake_streamlit.events)
                if kind == "markdown"
                and f'class="assessment-card-title">{name}</div>' in value
            )
            for name in card_names
        ]
        self.assertEqual(card_positions, sorted(card_positions))
        self.assertEqual(fake_streamlit.column_counts, [2])
        growth_button = fake_streamlit.events.index(
            ("button", "assessment-evidence-growth")
        )
        growth_evidence = fake_streamlit.events.index(("markdown", "### Growth"))
        risk_card = card_positions[3]
        self.assertLess(growth_button, growth_evidence)
        self.assertLess(growth_evidence, risk_card)
        self.assertEqual(
            sum(
                kind == "markdown" and value.startswith("### ")
                for kind, value in fake_streamlit.events
            ),
            1,
        )
        self.assertEqual(
            fake_streamlit.session_state["selected_evidence_indicator"],
            "growth",
        )

    def test_mobile_evidence_selection_switches_and_toggles_without_report_rebuild(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        switched_streamlit = _FakeStreamlit(
            _dashboard_report(),
            click_button_key="assessment-evidence-growth",
            selected_indicator="financial_quality",
            layout_mode="Mobile",
        )
        with patch.dict(sys.modules, {"streamlit": switched_streamlit}), patch(
            "investment_research.main.build_report"
        ) as build_report:
            runpy.run_path(str(app_path), run_name="feature_13mobile_switch_test")

        self.assertEqual(
            switched_streamlit.session_state["selected_evidence_indicator"],
            "growth",
        )
        self.assertIn(("markdown", "### Growth"), switched_streamlit.events)
        self.assertNotIn(
            ("markdown", "### Financial Quality"),
            switched_streamlit.events,
        )
        build_report.assert_not_called()

        closed_streamlit = _FakeStreamlit(
            _dashboard_report(),
            click_button_key="assessment-evidence-growth",
            selected_indicator="growth",
            layout_mode="Mobile",
        )
        with patch.dict(sys.modules, {"streamlit": closed_streamlit}), patch(
            "investment_research.main.build_report"
        ) as build_report:
            runpy.run_path(str(app_path), run_name="feature_13mobile_toggle_test")

        self.assertIsNone(closed_streamlit.session_state["selected_evidence_indicator"])
        self.assertNotIn(("markdown", "### Growth"), closed_streamlit.events)
        build_report.assert_not_called()

    def test_layout_change_reuses_saved_report_without_provider_calls(self):
        fake_streamlit = _FakeStreamlit(
            _dashboard_report(),
            selected_indicator="risk",
            layout_mode="Mobile",
        )
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.main.build_report"
        ) as build_report, patch(
            "investment_research.gemini_provider.generate_analysis"
        ) as company_provider, patch(
            "investment_research.gemini_provider.generate_market_review"
        ) as market_provider, patch(
            "investment_research.gemini_provider.generate_bull_bear"
        ) as bull_bear_provider, patch(
            "investment_research.tavily_provider.search"
        ) as search, patch(
            "investment_research.news.requests.get"
        ) as marketaux_request, patch(
            "investment_research.ticker_resolution.resolve_security_input"
        ) as resolver:
            runpy.run_path(str(app_path), run_name="feature_13layout_only_test")

        self.assertEqual(fake_streamlit.session_state["selected_evidence_indicator"], "risk")
        self.assertIn(("markdown", "### Risk"), fake_streamlit.events)
        for provider in (
            build_report,
            company_provider,
            market_provider,
            bull_bear_provider,
            search,
            marketaux_request,
            resolver,
        ):
            provider.assert_not_called()

    def test_evidence_selection_switches_and_toggles_without_rebuilding_report(self):
        fake_streamlit = _FakeStreamlit(
            _dashboard_report(),
            click_button_key="assessment-evidence-volatility",
            selected_indicator="financial_quality",
        )
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.main.build_report"
        ) as build_report:
            runpy.run_path(str(app_path), run_name="feature_13d_switch_test")

        self.assertEqual(
            fake_streamlit.session_state["selected_evidence_indicator"],
            "volatility",
        )
        self.assertIn(("markdown", "### Volatility"), fake_streamlit.events)
        self.assertNotIn(("markdown", "### Financial Quality"), fake_streamlit.events)
        build_report.assert_not_called()

        toggle_streamlit = _FakeStreamlit(
            _dashboard_report(),
            click_button_key="assessment-evidence-volatility",
            selected_indicator="volatility",
        )
        with patch.dict(sys.modules, {"streamlit": toggle_streamlit}), patch(
            "investment_research.main.build_report"
        ) as build_report:
            runpy.run_path(str(app_path), run_name="feature_13d_toggle_test")

        self.assertIsNone(toggle_streamlit.session_state["selected_evidence_indicator"])
        self.assertNotIn(("markdown", "### Volatility"), toggle_streamlit.events)
        build_report.assert_not_called()

    def test_stock_checker_branding_and_assessment_style_categories(self):
        fake_streamlit = _FakeStreamlit(_dashboard_report())
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}):
            runpy.run_path(str(app_path), run_name="feature_13e_branding_test")

        self.assertEqual(fake_streamlit.page_config, {
            "page_title": "Stock Checker",
            "page_icon": "static/stock_checker_icon.png",
        })
        self.assertEqual(fake_streamlit.title_calls, ["Stock Checker"])
        css = "\n".join(fake_streamlit.markdown_calls)
        self.assertEqual(len(fake_streamlit.html_calls), 1)
        head_script, html_kwargs = fake_streamlit.html_calls[0]
        self.assertIn('["manifest", "/app/static/stock_checker_manifest.json"]', head_script)
        self.assertIn('["apple-touch-icon", "/app/static/stock_checker_icon.png"]', head_script)
        self.assertTrue(html_kwargs["unsafe_allow_javascript"])
        manifest_path = Path(__file__).resolve().parents[1] / "static/stock_checker_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["name"], "Stock Checker")
        self.assertEqual(manifest["short_name"], "Stock Checker")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["icons"][0]["src"], "/app/static/stock_checker_icon.png")
        self.assertEqual(manifest["icons"][0]["type"], "image/png")
        for category in ("positive", "neutral", "caution", "muted"):
            self.assertIn(f".assessment-{category}", css)
        self.assertIn("height: 190px", css)
        self.assertIn("overflow-y: auto", css)
        self.assertIn("assessment-card-driver", css)

    def test_company_description_is_escaped_and_missing_description_is_omitted(self):
        report = _dashboard_report()
        report["company"]["description"] = "<script>alert('x')</script> Company overview."
        with_description = _FakeStreamlit(report)
        _run_app(with_description)
        description_markup = next(
            markup for markup in with_description.markdown_calls
            if 'class="company-description"' in markup
            and markup.startswith("<div")
        )
        self.assertIn("&lt;script&gt;", description_markup)
        self.assertNotIn("<script>", description_markup)

        report["company"].pop("description")
        without_description = _FakeStreamlit(report)
        _run_app(without_description)
        self.assertFalse(any(
            'class="company-description"' in markup
            for markup in without_description.markdown_calls
        ))

    def test_company_description_is_limited_to_five_complete_sentences(self):
        fake_streamlit = _FakeStreamlit({})
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}):
            app_globals = runpy.run_path(
                str(app_path), run_name="feature_13e_sentence_limit_test",
            )
        limit_description = app_globals["limit_company_description"]

        three_sentences = "First sentence. Second sentence! Third sentence?"
        five_sentences = (
            "First sentence. Second sentence. Third sentence. "
            "Fourth sentence. Fifth sentence."
        )
        six_sentences = f"{five_sentences} Sixth sentence."
        self.assertEqual(limit_description(three_sentences), three_sentences)
        self.assertEqual(limit_description(five_sentences), five_sentences)
        self.assertEqual(limit_description(six_sentences), five_sentences)
        self.assertEqual(
            limit_description("Dr. Lee joined Example Inc. It grew. Another result."),
            "Dr. Lee joined Example Inc. It grew. Another result.",
        )
        self.assertEqual(
            limit_description("U.S. growth is steady. Markets responded."),
            "U.S. growth is steady. Markets responded.",
        )
        self.assertIsNone(limit_description(None))

    def test_loading_and_completed_views_share_prepared_description_without_extra_lookup(self):
        description = (
            "First sentence. Second sentence. Third sentence. "
            "Fourth sentence. Fifth sentence. Sixth sentence."
        )
        report = _dashboard_report()
        report["company"]["description"] = description
        fake_streamlit = _FakeStreamlit({}, submitted=True, ticker="AAPL")
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.ticker_resolution.resolve_security_input",
            return_value=TickerResolution(status="resolved", ticker="AAPL"),
        ), patch(
            "investment_research.main.get_company_info",
            return_value=report["company"],
        ) as get_company_info, patch(
            "investment_research.main.build_report",
            return_value=report,
        ) as build_report:
            runpy.run_path(str(app_path), run_name="feature_13e_shared_description_test")

        expected = (
            "First sentence. Second sentence. Third sentence. "
            "Fourth sentence. Fifth sentence."
        )
        get_company_info.assert_called_once_with("AAPL")
        build_report.assert_called_once_with(
            "AAPL", preloaded_company=report["company"]
        )
        self.assertEqual(report["company"]["description"], expected)

        loading_markup = next(
            event[1]
            for event in fake_streamlit.placeholders[0].containers[0].events
            if event[0] == "markdown"
        )
        completed_markup = next(
            markup for markup in fake_streamlit.markdown_calls
            if markup.startswith('<div class="company-description">')
        )
        expected_markup = expected
        self.assertIn(expected_markup, loading_markup)
        self.assertEqual(
            loading_markup.split('<div class="company-description">', 1)[1].split("</div>", 1)[0],
            completed_markup.split('<div class="company-description">', 1)[1].split("</div>", 1)[0],
        )
        self.assertEqual(completed_markup, f'<div class="company-description">{expected_markup}</div>')
        self.assertNotIn("Read full company description", str(fake_streamlit.expanders))
        self.assertFalse(any(
            "company description" in title.lower()
            for title, _ in fake_streamlit.expanders
        ))

        styles = next(
            markup for markup in fake_streamlit.markdown_calls
            if ".company-description {" in markup
        )
        self.assertNotIn("-webkit-line-clamp", styles)
        self.assertNotIn("completed-company-description", styles)

    def test_loading_message_is_selected_locally_without_provider_calls(self):
        fake_streamlit = _FakeStreamlit(
            {"company": {"name": "Apple Inc.", "description": "Company description."}},
        )
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.gemini_provider.generate_analysis"
        ) as company_provider, patch(
            "investment_research.gemini_provider.generate_market_review"
        ) as market_provider, patch("investment_research.tavily_provider.search") as search:
            app_globals = runpy.run_path(str(app_path), run_name="feature_13e_loading_test")
            message = app_globals["_loading_message"]()
        self.assertGreaterEqual(len(app_globals["LOADING_MESSAGES"]), 8)
        self.assertIn(message, app_globals["LOADING_MESSAGES"])
        company_provider.assert_not_called()
        market_provider.assert_not_called()
        search.assert_not_called()

    def test_analysis_submission_builds_report_once_and_uses_local_loading_copy(self):
        report = _dashboard_report()
        report["company"]["description"] = "Company overview."
        fake_streamlit = _FakeStreamlit(
            {},
            submitted=True,
            ticker="AAPL",
        )
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.ticker_resolution.resolve_security_input",
            return_value=TickerResolution(status="resolved", ticker="AAPL"),
        ), patch(
            "investment_research.main.get_company_info",
            return_value=report["company"],
        ) as get_company_info, patch(
            "investment_research.main.build_report",
            return_value=report,
        ) as build_report, patch(
            "investment_research.gemini_provider.generate_analysis"
        ) as company_provider, patch(
            "investment_research.gemini_provider.generate_market_review"
        ) as market_provider, patch("investment_research.tavily_provider.search") as search:
            runpy.run_path(str(app_path), run_name="feature_13e_submit_test")

        get_company_info.assert_called_once_with("AAPL")
        build_report.assert_called_once_with("AAPL", preloaded_company=report["company"])
        self.assertTrue(fake_streamlit.info_calls)
        self.assertEqual(fake_streamlit.spinner_labels, ["Checking AAPL..."])
        loading_copy = "\n".join(fake_streamlit.loading_caption_calls)
        self.assertIn("While you wait", loading_copy)
        self.assertTrue("Fun fact:" in loading_copy or "Market joke:" in loading_copy)
        self.assertIn("Company overview.", "\n".join(fake_streamlit.markdown_calls))
        company_provider.assert_not_called()
        market_provider.assert_not_called()
        search.assert_not_called()

    def test_loading_description_precedes_build_and_company_lookup_runs_once(self):
        description = "Existing company description."
        provider_info = {
            "symbol": "AAPL",
            "longName": "Apple Inc.",
            "quoteType": "EQUITY",
            "exchange": "NMS",
            "longBusinessSummary": description,
        }

        class ProviderTicker:
            info_reads = 0

            @property
            def info(self):
                self.info_reads += 1
                return provider_info

        provider_ticker = ProviderTicker()
        report = _dashboard_report()
        report["company"]["description"] = description
        fake_streamlit = _FakeStreamlit({}, submitted=True, ticker="AAPL")
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        preloaded_companies = []

        def build_after_loading(ticker, *, preloaded_company):
            self.assertEqual(ticker, "AAPL")
            preloaded_companies.append(preloaded_company)
            self.assertEqual(preloaded_company["description"], description)
            placeholder = fake_streamlit.placeholders[0]
            self.assertEqual(len(placeholder.containers), 1)
            self.assertIn(
                description,
                placeholder.containers[0].events[0][1],
            )
            self.assertEqual(
                fake_streamlit.loading_events[-3:][0],
                ("divider",),
            )
            self.assertEqual(fake_streamlit.loading_events[-2], ("caption", "While you wait"))
            self.assertIn(
                fake_streamlit.loading_events[-1][1],
                fake_streamlit.loading_messages,
            )
            return report

        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.fetcher.yf.Ticker",
            return_value=provider_ticker,
        ) as ticker_lookup, patch(
            "investment_research.main.build_report",
            side_effect=build_after_loading,
        ) as build_report, patch(
            "investment_research.ticker_resolution.yf.Search",
        ) as symbol_search:
            runpy.run_path(str(app_path), run_name="feature_13e_loading_description_test")

        ticker_lookup.assert_called_once_with("AAPL")
        self.assertEqual(provider_ticker.info_reads, 1)
        build_report.assert_called_once()
        self.assertEqual(build_report.call_args.args[0], "AAPL")
        self.assertIs(build_report.call_args.kwargs["preloaded_company"], preloaded_companies[0])
        self.assertEqual(
            build_report.call_args.kwargs["preloaded_company"]["description"],
            description,
        )
        self.assertTrue(fake_streamlit.placeholder_cleared)
        symbol_search.assert_not_called()

    def test_invalid_ticker_does_not_start_report_build(self):
        fake_streamlit = _FakeStreamlit({}, submitted=True, ticker="NOPE")
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.ticker_resolution.resolve_security_input",
            return_value=TickerResolution(status="not_found"),
        ), patch(
            "investment_research.main.get_company_info",
            return_value=None,
        ) as lookup, patch(
            "investment_research.main.build_report"
        ) as build_report:
            runpy.run_path(str(app_path), run_name="feature_13e_invalid_ticker_test")

        lookup.assert_called_once_with("NOPE")
        build_report.assert_not_called()
        self.assertIn(
            "Ticker or company not found. Check the symbol or company name and try again.",
            fake_streamlit.error_calls,
        )

    def test_canonical_ticker_rate_limit_shows_provider_message_without_search(self):
        fake_streamlit = _FakeStreamlit({}, submitted=True, ticker="AAPL")
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.main.get_company_info",
            side_effect=fetcher.YahooRateLimitError("temporarily rate-limited"),
        ), patch(
            "investment_research.ticker_resolution.yf.Search",
        ) as symbol_search, patch(
            "investment_research.main.build_report",
        ) as build_report:
            runpy.run_path(str(app_path), run_name="yahoo_rate_limit_ui_test")

        self.assertIn(
            "Market data provider is temporarily rate-limited. Please try again shortly.",
            fake_streamlit.error_calls,
        )
        symbol_search.assert_not_called()
        build_report.assert_not_called()

    def test_non_us_unsuffixed_ticker_searches_once_and_reuses_canonical_lookup(self):
        fake_streamlit = _FakeStreamlit({}, submitted=True, ticker="BARC")
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        initial_company = {
            "ticker": "BARC",
            "name": "Barclays PLC",
            "country": "United Kingdom",
        }
        canonical_company = {
            "ticker": "BARC.L",
            "name": "Barclays PLC",
            "country": "United Kingdom",
        }
        search_response = SimpleNamespace(
            quotes=[
                {
                    "symbol": "BARC.L",
                    "longname": "Barclays PLC",
                    "quoteType": "EQUITY",
                    "exchDisp": "London",
                }
            ]
        )
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}), patch(
            "investment_research.main.get_company_info",
            side_effect=[initial_company, canonical_company],
        ) as company_lookup, patch(
            "investment_research.main.build_report",
            return_value=None,
        ) as build_report, patch(
            "investment_research.ticker_resolution.yf.Search",
            return_value=search_response,
        ) as symbol_search:
            runpy.run_path(str(app_path), run_name="non_us_ticker_resolution_test")

        self.assertEqual(
            [call.args for call in company_lookup.call_args_list],
            [("BARC",), ("BARC.L",)],
        )
        symbol_search.assert_called_once()
        build_report.assert_called_once_with(
            "BARC.L",
            preloaded_company=canonical_company,
        )

    def test_missing_loading_description_shows_only_local_fun_fact(self):
        report = {"company": {"ticker": "AAPL", "name": "Apple Inc.", "description": None}}
        fake_streamlit = _FakeStreamlit(report)
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(sys.modules, {"streamlit": fake_streamlit}):
            app_globals = runpy.run_path(str(app_path), run_name="feature_13e_missing_description_test")
            placeholder = fake_streamlit.empty()
            app_globals["_render_loading_company"](placeholder, report["company"])

        self.assertIn(placeholder.parent.loading_messages[-1], app_globals["LOADING_MESSAGES"])
        self.assertEqual(placeholder.markdown_calls, [])


def _dashboard_report():
    from investment_research.assessment_display import ASSESSMENT_INDICATORS

    return {
        "ticker": "AAPL",
        "company": {"name": "Apple Inc.", "price": 200, "market_cap": 1_000_000},
        "assessment": {
            "indicators": {
                key: {
                    "label": "High" if key == "volatility" else "Moderate",
                    "drivers": [f"{name} driver."],
                }
                for key, name in ASSESSMENT_INDICATORS
            }
        },
        "ratios": {
            "valuation": {"trailing_pe": 20.5, "trailing_pe_status": "available"},
        },
        "price_performance": {
            "daily_returns": [0.01] * 400,
            "annualized_volatility": 0.48,
            "beta": 1.71,
            "max_drawdown": -0.374,
            "returns": {"1 Month": 0.094, "6 Months": 0.066, "1 Year": -0.193},
            "range": {"current_price": 200, "high": 250, "low": 150},
        },
    }


def _run_app(fake_streamlit):
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    with patch.dict(sys.modules, {"streamlit": fake_streamlit}):
        runpy.run_path(str(app_path), run_name="feature_13d_layout_test")


class _FakeColumn:
    def __init__(self, parent):
        self.parent = parent

    def metric(self, *_args, **_kwargs):
        return None

    def markdown(self, value, **_kwargs):
        self.parent.markdown(value, **_kwargs)

    def button(self, label, *, key, **kwargs):
        self.parent.buttons.append((label, key, kwargs))
        self.parent.events.append(("button", key))
        return False

    def container(self, **_kwargs):
        return nullcontext()


class _FakeStreamlit:
    def __init__(
        self,
        saved_report,
        click_button_key=None,
        selected_indicator=None,
        *,
        submitted=False,
        ticker="",
        layout_mode=None,
    ):
        self.session_state = {"research_report": saved_report}
        self.submitted = submitted
        self.ticker = ticker
        self.layout_mode = layout_mode
        self.click_button_key = click_button_key
        if selected_indicator:
            self.session_state["selected_evidence_indicator"] = selected_indicator
        if click_button_key:
            clicked_indicator = click_button_key.removeprefix("assessment-evidence-")
            current = self.session_state.get("selected_evidence_indicator")
            self.session_state["selected_evidence_indicator"] = (
                None if current == clicked_indicator else clicked_indicator
            )
        self.expanders = []
        self.buttons = []
        self.markdown_calls = []
        self.write_calls = []
        self.info_calls = []
        self.events = []
        self.tables = []
        self.error_calls = []
        self.placeholder_cleared = False
        self.loading_markdown_calls = []
        self.page_config = {}
        self.title_calls = []
        self.spinner_labels = []
        self.loading_caption_calls = []
        self.loading_events = []
        self.loading_messages = []
        self.placeholders = []
        self.segmented_controls = []
        self.column_counts = []
        self.html_calls = []

    def set_page_config(self, **_kwargs):
        self.page_config = _kwargs

    def title(self, value, **_kwargs):
        self.title_calls.append(value)

    def write(self, value, *_args, **_kwargs):
        self.write_calls.append(str(value))
        self.events.append(("write", str(value)))

    def subheader(self, *_args, **_kwargs):
        return None

    def columns(self, count):
        self.column_counts.append(count)
        return [_FakeColumn(self) for _ in range(count)]

    def markdown(self, value, **_kwargs):
        self.markdown_calls.append(str(value))
        self.events.append(("markdown", str(value)))

    def html(self, value, **kwargs):
        self.html_calls.append((str(value), kwargs))

    def caption(self, *_args, **_kwargs):
        return None

    def info(self, value, *_args, **_kwargs):
        self.info_calls.append(str(value))

    def error(self, value, *_args, **_kwargs):
        self.error_calls.append(str(value))

    def empty(self):
        placeholder = _FakePlaceholder(self)
        self.placeholders.append(placeholder)
        return placeholder

    def table(self, *_args, **_kwargs):
        rows = _args[0] if _args else _kwargs.get("data")
        self.tables.append(rows)
        self.events.append(("table", rows))

    def text_input(self, *_args, **_kwargs):
        return self.ticker

    def form(self, *_args, **_kwargs):
        return nullcontext()

    def form_submit_button(self, *_args, **_kwargs):
        return self.submitted

    def segmented_control(self, label, options, *, key, **_kwargs):
        self.segmented_controls.append((label, options, key))
        value = self.layout_mode or self.session_state.get(key, options[0])
        self.session_state[key] = value
        return value

    def expander(self, title, **kwargs):
        self.expanders.append((title, kwargs))
        return nullcontext()

    def button(self, label, *, key, **kwargs):
        self.buttons.append((label, key, kwargs))
        self.events.append(("button", key))
        return False

    def container(self, **_kwargs):
        return nullcontext()

    def spinner(self, *_args, **_kwargs):
        self.spinner_labels.append(_args[0] if _args else "")
        return nullcontext()


class _FakePlaceholder:
    def __init__(self, parent):
        self.parent = parent
        self.markdown_calls = []
        self.info_calls = []
        self.containers = []

    def container(self):
        container = _FakeLoadingContainer(self)
        self.containers.append(container)
        return container

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def markdown(self, value, **_kwargs):
        text = str(value)
        self.markdown_calls.append(text)
        self.parent.loading_markdown_calls.append(text)
        self.parent.markdown_calls.append(text)

    def info(self, value, **_kwargs):
        text = str(value)
        self.info_calls.append(text)
        self.parent.info_calls.append(text)

    def divider(self):
        self.parent.loading_events.append(("divider",))

    def caption(self, value, **_kwargs):
        text = str(value)
        self.parent.loading_caption_calls.append(text)
        self.parent.loading_events.append(("caption", text))
        if text != "While you wait":
            self.parent.loading_messages.append(text)

    def empty(self):
        self.parent.placeholder_cleared = True


class _FakeLoadingContainer:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.events = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def markdown(self, value, **_kwargs):
        text = str(value)
        self.events.append(("markdown", text))
        self.placeholder.markdown_calls.append(text)
        self.placeholder.parent.loading_markdown_calls.append(text)
        self.placeholder.parent.markdown_calls.append(text)

    def divider(self):
        self.events.append(("divider",))
        self.placeholder.parent.loading_events.append(("divider",))

    def caption(self, value, **_kwargs):
        text = str(value)
        self.events.append(("caption", text))
        self.placeholder.parent.loading_caption_calls.append(text)
        self.placeholder.parent.loading_events.append(("caption", text))
        if text != "While you wait":
            self.placeholder.parent.loading_messages.append(text)


if __name__ == "__main__":
    unittest.main()
