import json
import unittest
from unittest.mock import patch

import requests

from investment_research import display
from investment_research import main
from investment_research.news import (
    DESCRIPTION_MAX_CHARACTERS,
    MIN_RELEVANCE_MATCH_SCORE,
    format_article_date,
    get_company_news,
)


class FakeResponse:
    """Small requests.Response stand-in for tests that never call the network."""

    def __init__(self, payload=None, status_error=None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def article(
    title="Apple publishes quarterly update",
    url="https://example.com/apple-update",
    description="Apple reported its latest quarterly results.",
    source="Example News",
    published_at="2026-09-02T14:32:17Z",
    entities=None,
):
    value = {
        "title": title,
        "url": url,
        "description": description,
        "source": source,
        "published_at": published_at,
    }
    value["entities"] = entities if entities is not None else [
        {"symbol": "AAPL", "match_score": 82.0}
    ]
    return value


class NewsTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict("os.environ", {"MARKETAUX_API_KEY": "test-token"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_valid_response_returns_three_standardised_articles_and_one_request(self):
        payload = {"data": [article(f"Headline {number}", f"https://example.com/{number}") for number in range(3)]}
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)) as request:
            result = get_company_news("aapl")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["articles"]), 3)
        self.assertEqual(set(result["articles"][0]), {"title", "source", "published_at", "description", "url"})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.kwargs["params"]["symbols"], "AAPL")
        self.assertEqual(request.call_args.kwargs["params"]["limit"], 3)
        self.assertEqual(
            request.call_args.kwargs["params"]["min_match_score"],
            MIN_RELEVANCE_MATCH_SCORE,
        )
        self.assertEqual(
            request.call_args.kwargs["params"]["sort"],
            "entity_match_score",
        )
        self.assertEqual(request.call_args.kwargs["params"]["sort_order"], "desc")
        self.assertRegex(
            request.call_args.kwargs["params"]["published_after"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        )
        self.assertNotIn("test-token", json.dumps(result))

    def test_fewer_than_three_articles_are_allowed(self):
        payload = {"data": [article()]}
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["articles"]), 1)

    def test_empty_response_is_distinguished_from_service_failure(self):
        with patch("investment_research.news.requests.get", return_value=FakeResponse({"data": []})):
            result = get_company_news("AAPL")
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["articles"], [])

    def test_missing_api_key_is_graceful_and_does_not_request(self):
        with patch.dict("os.environ", {}, clear=True), patch("investment_research.news.requests.get") as request:
            result = get_company_news("AAPL")
        self.assertEqual(result["status"], "unavailable")
        request.assert_not_called()

    def test_http_api_and_malformed_response_fail_gracefully(self):
        cases = [
            FakeResponse({}, requests.RequestException("server error")),
            FakeResponse({"error": {"message": "rate limit"}}),
            FakeResponse({"data": "not a list"}),
            FakeResponse(json.JSONDecodeError("bad json", "", 0)),
        ]
        for response in cases:
            with self.subTest(response=response), patch(
                "investment_research.news.requests.get", return_value=response
            ):
                result = get_company_news("AAPL")
                self.assertEqual(result["status"], "unavailable")

    def test_timeout_and_network_errors_fail_gracefully(self):
        for error in (requests.Timeout(), requests.ConnectionError()):
            with self.subTest(error=error), patch(
                "investment_research.news.requests.get", side_effect=error
            ):
                result = get_company_news("AAPL")
                self.assertEqual(result["status"], "unavailable")

    def test_missing_fields_are_safe_and_articles_without_titles_are_skipped(self):
        payload = {
            "data": [
                {"description": "No title means this cannot be displayed."},
                article(source="", description=None, published_at=None, url=None),
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(len(result["articles"]), 1)
        self.assertIsNone(result["articles"][0]["url"])
        self.assertEqual(result["articles"][0]["source"], "")
        self.assertIsNone(result["articles"][0]["published_at"])
        self.assertEqual(result["articles"][0]["description"], "")

    def test_duplicate_urls_and_normalised_headlines_are_removed(self):
        payload = {
            "data": [
                article("Same headline", "https://example.com/one"),
                article("Same headline", "https://example.com/two"),
                article("Another headline", "https://example.com/one"),
                article("Different headline", "https://example.com/three"),
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(
            [item["title"] for item in result["articles"]],
            ["Same headline", "Different headline"],
        )

    def test_entity_association_is_used_without_ticker_text_matching(self):
        payload = {
            "data": [
                article("AAPL appears in text", entities=[{"symbol": "MSFT"}]),
                article(
                    "Correct entity",
                    "https://example.com/correct",
                    entities=[{"symbol": "AAPL", "match_score": 82.0}],
                ),
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual([item["title"] for item in result["articles"]], ["Correct entity"])

    def test_strong_entity_match_is_retained_and_weak_match_is_rejected(self):
        payload = {
            "data": [
                article(
                    "Strong company story",
                    "https://example.com/strong",
                    entities=[{"symbol": "AAPL", "match_score": 50.0}],
                ),
                article(
                    "Incidental mention",
                    "https://example.com/weak",
                    entities=[{"symbol": "AAPL", "match_score": 49.99}],
                ),
                article(
                    "Wrong company story",
                    "https://example.com/wrong",
                    entities=[{"symbol": "MSFT", "match_score": 99.0}],
                ),
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual([item["title"] for item in result["articles"]], ["Strong company story"])

    def test_strong_title_entity_evidence_is_retained(self):
        payload = {
            "data": [
                article(
                    "Apple announces a company-specific update",
                    entities=[{
                        "symbol": "AAPL",
                        "match_score": 55.0,
                        "highlights": [{"highlighted_in": "title"}],
                    }],
                )
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["articles"]), 1)

    def test_missing_match_score_is_rejected_safely(self):
        payload = {
            "data": [
                article(
                    "Unscored article",
                    entities=[{"symbol": "AAPL"}],
                )
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["articles"], [])

    def test_only_one_relevant_article_is_not_filled_with_irrelevant_stories(self):
        payload = {
            "data": [
                article(
                    "Relevant company article",
                    "https://example.com/relevant",
                    entities=[{"symbol": "AAPL", "match_score": 70.0}],
                ),
                article(
                    "Broad market article",
                    "https://example.com/broad",
                    entities=[{"symbol": "AAPL", "match_score": 25.0}],
                ),
                article(
                    "Another broad market article",
                    "https://example.com/broad-2",
                    entities=[{"symbol": "AAPL", "match_score": 20.0}],
                ),
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual([item["title"] for item in result["articles"]], ["Relevant company article"])

    def test_all_three_strong_matches_are_returned(self):
        payload = {
            "data": [
                article(
                    f"Strong article {number}",
                    f"https://example.com/strong-{number}",
                    entities=[{"symbol": "AAPL", "match_score": 60.0 + number}],
                )
                for number in range(3)
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(len(result["articles"]), 3)

    def test_no_relevant_articles_returns_the_normal_empty_state(self):
        payload = {
            "data": [
                article(
                    "Incidental market story",
                    entities=[{"symbol": "AAPL", "match_score": 10.0}],
                ),
                article(
                    "Wrong entity story",
                    entities=[{"symbol": "MSFT", "match_score": 90.0}],
                ),
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["articles"], [])

    def test_articles_are_sorted_newest_first_and_bad_dates_go_last(self):
        payload = {
            "data": [
                article(
                    "Older article",
                    "https://example.com/older",
                    published_at="2026-08-27T09:00:00Z",
                ),
                article(
                    "Malformed date article",
                    "https://example.com/malformed",
                    published_at="not-a-date",
                ),
                article(
                    "Newest article",
                    "https://example.com/newest",
                    published_at="2026-08-29T09:00:00Z",
                ),
                article(
                    "Missing date article",
                    "https://example.com/missing",
                    published_at=None,
                ),
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(
            [item["title"] for item in result["articles"]],
            [
                "Newest article",
                "Older article",
                "Malformed date article",
            ],
        )

    def test_ambiguous_ticker_does_not_use_naive_substring_matching(self):
        payload = {
            "data": [
                {
                    "title": "A broad story containing the letter C",
                    "url": "https://example.com/ambiguous",
                    "description": "This is not a company-specific story.",
                    "source": "Example News",
                    "published_at": "2026-09-02T14:32:17Z",
                    "entities": [{"symbol": "CAT", "match_score": 99.0}],
                }
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("C")
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["articles"], [])

    def test_description_drops_incomplete_trailing_fragment(self):
        payload = {
            "data": [
                article(
                    description=(
                        "Apple reported strong quarterly growth. "
                        "Naturally, Apple Inc."
                    )
                )
            ]
        }
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        self.assertEqual(
            result["articles"][0]["description"],
            "Apple reported strong quarterly growth.",
        )

    def test_description_is_shortened_at_a_word_boundary(self):
        long_description = " ".join(["A factual sentence with several words"] * 80)
        payload = {"data": [article(description=long_description)]}
        with patch("investment_research.news.requests.get", return_value=FakeResponse(payload)):
            result = get_company_news("AAPL")
        description = result["articles"][0]["description"]
        self.assertLessEqual(len(description), DESCRIPTION_MAX_CHARACTERS)
        self.assertFalse(description.endswith(" "))

    def test_date_formatting_handles_utc_and_malformed_values(self):
        self.assertEqual(format_article_date("2026-09-02T14:32:17Z"), "2 Sep 2026")
        self.assertEqual(format_article_date("not-a-date"), "Date unavailable")
        self.assertEqual(format_article_date(None), "Date unavailable")

    def test_display_uses_hyperlink_and_safe_url_fallback(self):
        linked = display.format_news_headline(
            "Headline", "https://example.com/story", supports_hyperlinks=True
        )
        plain = display.format_news_headline(
            "Headline", "https://example.com/story", supports_hyperlinks=False
        )
        without_url = display.format_news_headline("Headline", None, supports_hyperlinks=True)
        self.assertIn("\033]8;;https://example.com/story\a", linked)
        self.assertIn("Headline", linked)
        self.assertEqual(plain, "Headline")
        self.assertEqual(without_url, "Headline")

    def test_display_prints_unavailable_and_empty_states(self):
        with patch("builtins.print") as printer:
            display.print_news({"status": "unavailable", "message": "Recent news temporarily unavailable."})
            display.print_news({"status": "empty", "message": "No recent company-specific news found."})
        output = " ".join(str(call.args[0]) for call in printer.call_args_list if call.args)
        self.assertIn("Recent news temporarily unavailable.", output)
        self.assertIn("No recent company-specific news found.", output)

    def test_news_failure_does_not_break_normal_application_flow(self):
        """A news timeout is isolated after the rest of the report runs."""
        with patch("builtins.input", side_effect=["AAPL", "quit"]), \
             patch("investment_research.main.display.print_welcome"), \
             patch("investment_research.main.display.print_stock_info"), \
             patch("investment_research.main.display.print_company_overview"), \
             patch("investment_research.main.display.print_income_statement"), \
             patch("investment_research.main.display.print_balance_sheet"), \
             patch("investment_research.main.display.print_cash_flow"), \
             patch("investment_research.main.display.print_ratios"), \
             patch("investment_research.main.display.print_peer_comparison"), \
             patch("investment_research.main.display.print_performance"), \
             patch("investment_research.main.display.print_analyst_expectations"), \
             patch("investment_research.main.display.print_news") as print_news, \
             patch("investment_research.main.fetcher.get_stock_info", return_value={"ticker": "AAPL"}), \
             patch("investment_research.main.financials.get_financial_statements", return_value={}), \
             patch("investment_research.main.financials.get_ratios", return_value={}), \
             patch("investment_research.main.peers.fetch_peer_comparison", return_value={}), \
             patch("investment_research.main.performance.get_performance", return_value={}), \
             patch("investment_research.main.expectations.get_analyst_expectations", return_value={}), \
             patch(
                 "investment_research.main.news.get_company_news",
                 side_effect=requests.Timeout("Marketaux timed out"),
             ):
            main.run()

        print_news.assert_called_once_with({
            "status": "unavailable",
            "message": "Recent news temporarily unavailable.",
            "articles": [],
        })


if __name__ == "__main__":
    unittest.main()