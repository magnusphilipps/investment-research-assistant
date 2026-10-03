import unittest

from investment_research.assessment_display import (
    ASSESSMENT_INDICATORS,
    get_assessment_display,
    get_indicator_display,
    get_label_style,
)


class AssessmentDisplayTests(unittest.TestCase):
    def test_all_eight_indicators_are_extracted_in_dashboard_order(self):
        report = {
            "assessment": {
                "indicators": {
                    key: {"label": f"Label for {key}", "drivers": [f"Driver for {key}"]}
                    for key, _ in ASSESSMENT_INDICATORS
                }
            }
        }

        cards = get_assessment_display(report)

        self.assertEqual(len(cards), 8)
        self.assertEqual([card["name"] for card in cards], [
            "Valuation",
            "Financial Quality",
            "Growth",
            "Risk",
            "Volatility",
            "Market Environment",
            "Competitive Position",
            "Expectations",
        ])
        self.assertEqual(cards[0]["label"], "Label for valuation")

    def test_indicator_label_and_first_available_driver_are_preserved(self):
        card = get_indicator_display(
            {
                "assessment": {
                    "indicators": {
                        "growth": {
                            "label": "Strong",
                            "drivers": ["", None, "Revenue growth leads peers.", "Later driver."],
                        }
                    }
                }
            },
            "growth",
            "Growth",
        )

        self.assertEqual(card["label"], "Strong")
        self.assertEqual(card["driver"], "Revenue growth leads peers.")

    def test_missing_driver_is_empty(self):
        for indicator in ({"label": "Moderate"}, {"label": "Moderate", "drivers": [None, " "]}):
            with self.subTest(indicator=indicator):
                card = get_indicator_display(
                    {"assessment": {"indicators": {"growth": indicator}}},
                    "growth",
                    "Growth",
                )
                self.assertEqual(card["driver"], "")

    def test_na_indicator_is_safe_and_muted(self):
        card = get_indicator_display(
            {"assessment": {"indicators": {"risk": {"label": "N/A", "drivers": None}}}},
            "risk",
            "Risk",
        )

        self.assertEqual(card["label"], "N/A")
        self.assertEqual(card["driver"], "")
        self.assertEqual(card["style"], "muted")

    def test_display_data_does_not_include_hidden_scores(self):
        report = {
            "assessment": {
                "indicators": {
                    key: {
                        "label": "Fair",
                        "drivers": ["Valuation is in line with peers."],
                        "score": 99,
                    }
                    for key, _ in ASSESSMENT_INDICATORS
                }
            }
        }

        for card in get_assessment_display(report):
            self.assertNotIn("score", card)
            self.assertNotIn("score", card.values())
            self.assertEqual(set(card), {"name", "label", "driver", "style"})

    def test_missing_assessment_section_returns_na_cards_without_raising(self):
        for report in ({}, None, {"assessment": None}, {"assessment": {"indicators": None}}):
            with self.subTest(report=report):
                cards = get_assessment_display(report)
                self.assertEqual(len(cards), 8)
                self.assertTrue(all(card["label"] == "N/A" for card in cards))
                self.assertTrue(all(card["driver"] == "" for card in cards))

    def test_label_styles_are_semantic_visual_states(self):
        self.assertEqual(get_label_style("Favourable"), "positive")
        self.assertEqual(get_label_style("Fair"), "neutral")
        self.assertEqual(get_label_style("High"), "caution")
        self.assertEqual(get_label_style("N/A"), "muted")


if __name__ == "__main__":
    unittest.main()
