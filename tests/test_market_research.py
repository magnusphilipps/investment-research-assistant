import os
import unittest
from unittest.mock import patch

from investment_research import market_research, tavily_provider
from investment_research import display


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def valid_review(source_ids=None):
    return {
        "industry_overview": "The supplied evidence describes the industry.",
        "growth_drivers": ["Demand", "Investment", "Adoption"],
        "competitive_dynamics": ["Competition", "Technology", "Customers"],
        "industry_risks": ["Regulation", "Supply", "Macro conditions"],
        "market_outlook": "The evidence supports a cautious outlook.",
        "company_implications": ["Demand may change.", "Execution matters.", "Competition matters."],
        "sources_used": source_ids or ["S1"],
    }


class TavilyProviderTests(unittest.TestCase):
    def test_missing_key_returns_empty_without_request(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "investment_research.tavily_provider.requests.post"
        ) as request:
            self.assertEqual(tavily_provider.search("banking outlook"), [])
        request.assert_not_called()

    def test_successful_search_preserves_results_and_key_stays_out_of_output(self):
        payload = {"results": [{"title": "Industry report", "url": "https://example.com", "content": "Evidence"}]}
        with patch.dict(os.environ, {"TAVILY_API_KEY": "secret"}), patch(
            "investment_research.tavily_provider.requests.post",
            return_value=FakeResponse(payload),
        ) as request:
            result = tavily_provider.search("banking outlook")
        self.assertEqual(result, payload["results"])
        self.assertNotIn("secret", str(result))
        self.assertEqual(request.call_args.kwargs["json"]["api_key"], "secret")


class MarketResearchTests(unittest.TestCase):
    def test_known_companies_receive_narrow_economic_research_lenses(self):
        cases = [
            ({"name": "Materials Co.", "description": "Produces rare earth NdPr materials and permanent magnets."}, "rare earths"),
            ({"name": "Compute Co.", "description": "Builds AI infrastructure with GPU cloud and data center capacity."}, "AI infrastructure"),
            ({"name": "Devices Co.", "description": "Makes smartphones, wearables, and a digital ecosystem."}, "smartphones"),
            ({"name": "Bank Co.", "description": "Operates banking, lending, payments, and capital markets businesses."}, "large-bank"),
        ]
        for info, expected in cases:
            with self.subTest(info=info):
                self.assertIn(expected, market_research.build_research_focus(info)["industry"])

    def test_description_can_identify_multiple_material_markets(self):
        focus = market_research.build_research_focus({
            "industry": "Internet Content & Information",
            "description": "The company operates AI infrastructure and GPU cloud services, plus a payments platform.",
        })
        self.assertEqual(len(focus["markets"]), 2)
        self.assertIn("AI infrastructure", focus["industry"])
        self.assertIn("payments", focus["industry"])

    def test_missing_description_falls_back_without_inventing_a_market(self):
        focus = market_research.build_research_focus({
            "industry": "Internet Content & Information",
            "sector": "Communication Services",
        })
        self.assertEqual(focus["industry"], "Internet Content & Information")
        self.assertEqual(focus["markets"], [{"market": "Internet Content & Information"}])

    def test_nebius_like_description_overrides_broad_provider_industry(self):
        info = {
            "ticker": "NBIS",
            "name": "Nebius Group N.V.",
            "sector": "Communication Services",
            "industry": "Internet Content & Information",
            "description": (
                "Nebius builds full-stack infrastructure for AI, including large-scale "
                "GPU clusters, cloud platforms, and tools and services for developers. "
                "The company also provides an edtech platform and autonomous driving technology."
            ),
        }
        focus = market_research.build_research_focus(info)
        queries = market_research.build_queries(info)

        self.assertIn("AI infrastructure", focus["industry"])
        self.assertNotEqual(focus["industry"], "Internet Content & Information")
        self.assertTrue(all("Internet Content" not in query for query in queries))
        self.assertTrue(any("AI infrastructure" in query for query in queries))
        self.assertTrue(any("GPU" in query for query in queries))

    def test_queries_use_industry_and_current_year_without_ticker_specific_logic(self):
        queries = market_research.build_queries({
            "ticker": "XYZ",
            "name": "Regional Bank",
            "sector": "Financial Services",
            "industry": "Banks",
        })
        self.assertEqual(len(queries), 5)
        self.assertTrue(all("Banks" in query for query in queries[:4]))
        self.assertIn("value chain", queries[1])

    def test_cleaning_removes_invalid_and_duplicate_results(self):
        results = market_research.clean_evidence([
            {"title": "One", "url": "https://example.com/a", "content": " Text  here "},
            {"title": "One", "url": "https://example.com/b", "content": "Duplicate title"},
            {"title": "", "url": "https://example.com/c", "content": "No title"},
            {"title": "No content", "url": "https://example.com/d", "content": ""},
        ])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "S1")
        self.assertEqual(results[0]["source"], "example.com")

    def test_missing_metadata_and_empty_evidence_are_safe(self):
        self.assertEqual(market_research.build_queries({}), [])
        with patch("investment_research.market_research.tavily_provider.search", return_value=[]):
            result = market_research.get_market_review({"name": "Example"})
        self.assertEqual(result["status"], "unavailable")

    def test_successful_review_maps_only_valid_source_ids(self):
        raw = [{"title": "Evidence", "url": "https://example.com/a", "content": "Industry evidence"}]
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.market_research.tavily_provider.search", return_value=raw
        ), patch(
            "investment_research.market_research.gemini_provider.generate_market_review",
            return_value={"status": "ok", "review": valid_review()},
        ):
            result = market_research.get_market_review({"name": "Example", "industry": "Example industry"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sources"][0]["url"], "https://example.com/a")

    def test_unknown_source_ids_are_rejected(self):
        raw = [{"title": "Evidence", "url": "https://example.com/a", "content": "Industry evidence"}]
        invalid = valid_review(["S99"])
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.market_research.tavily_provider.search", return_value=raw
        ), patch(
            "investment_research.market_research.gemini_provider.generate_market_review",
            return_value={"status": "ok", "review": invalid},
        ):
            result = market_research.get_market_review({"name": "Example", "industry": "Example industry"})
        self.assertEqual(result["status"], "unavailable")

    def test_source_metadata_remains_internal(self):
        raw = [{"title": "Evidence", "url": "https://example.com/a", "content": "Industry evidence"}]
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "investment_research.market_research.tavily_provider.search", return_value=raw
        ), patch(
            "investment_research.market_research.gemini_provider.generate_market_review",
            return_value={"status": "ok", "review": valid_review()},
        ):
            result = market_research.get_market_review({"name": "Example", "industry": "Example industry"})
        self.assertEqual(result["sources"][0]["url"], "https://example.com/a")
        self.assertEqual(result["review"]["sources_used"], ["S1"])

    def test_display_hides_source_ids_and_urls(self):
        result = {
            "status": "ok",
            "review": {
                **valid_review(),
                "industry_overview": "Evidence (S1, S2) is available at https://example.com/report.",
                "company_implications": ["Demand may rise (S1)."],
            },
            "sources": [{"id": "S1", "url": "https://example.com/report", "source": "Example"}],
        }
        with patch("builtins.print") as printer:
            display.print_market_review(result, "Example")
        output = "\n".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertNotIn("Sources", output)
        self.assertNotIn("https://example.com/report", output)
        self.assertNotRegex(output, r"\bS\d+\b")
        self.assertIn("Industry Overview", output)

    def test_long_bullets_wrap_at_terminal_width_without_mutating_result(self):
        bullet = (
            "Rising competition from customer-designed custom silicon and expanding "
            "alternatives may require sustained technological innovation to maintain "
            "market share and pricing power."
        )
        result = {"status": "ok", "review": {**valid_review(), "growth_drivers": [bullet]}, "sources": []}
        with patch("builtins.print") as printer:
            display.print_market_review(result, "Example")
        output_lines = [
            line
            for call in printer.call_args_list
            if call.args and isinstance(call.args[0], str)
            for line in str(call.args[0]).splitlines()
        ]
        start = output_lines.index("  Growth Drivers") + 1
        end = output_lines.index("  Competitive Dynamics")
        bullet_lines = output_lines[start:end]
        self.assertGreater(len(bullet_lines), 1)
        self.assertTrue(all(len(line) <= 80 for line in bullet_lines))
        self.assertEqual(bullet_lines[0][:4], "  • ")
        self.assertTrue(all(not line.startswith("  • ") for line in bullet_lines[1:]))
        self.assertEqual(result["review"]["growth_drivers"], [bullet])

    def test_conflicting_estimates_are_kept_separate_for_grounded_reasoning(self):
        results = market_research.clean_evidence([
            {
                "title": "Narrow market estimate",
                "url": "https://example.com/narrow",
                "content": "The narrowly defined segment is estimated at $760 billion.",
            },
            {
                "title": "Broad market estimate",
                "url": "https://example.com/broad",
                "content": "The broader market is estimated at over $1.5 trillion.",
            },
        ])
        self.assertEqual(len(results), 2)
        self.assertNotIn("$760 billion to over $1.5 trillion", " ".join(item["content"] for item in results))


if __name__ == "__main__":
    unittest.main()
