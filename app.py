"""Streamlit entry point for the stock assessment dashboard."""

from html import escape
import logging
import os
from random import choice
import re
from typing import Any

from dotenv import load_dotenv
import streamlit as st

load_dotenv(".env")

from investment_research import (
    assessment_display,
    display,
    main,
    qualitative_display,
    ticker_resolution,
    diagnostics,
)

LOGGER = logging.getLogger(__name__)
PROVIDER_API_KEY_NAMES = (
    "GOOGLE_API_KEY",
    "TAVILY_API_KEY",
    "MARKETAUX_API_KEY",
)


LOADING_MESSAGES = (
    "Fun fact: The first stock ticker tape machine appeared in 1867.",
    "Market joke: Analysts have predicted nine of the last five recessions.",
    "Fun fact: The NYSE began under a buttonwood tree in 1792.",
    "Market joke: A long-term investor is someone who forgot their password.",
    "Fun fact: The word 'stock' once referred to wooden tally sticks used to record debt.",
    "Market joke: The market is a device for transferring money from the impatient to the patient.",
    "Fun fact: The Dow Jones Industrial Average started with 12 companies.",
    "Market joke: Diversification is what happens when you run out of ticker symbols to watch.",
    "Fun fact: Some early exchanges traded commodities as well as company shares.",
    "Market joke: The only predictable thing about markets is how confidently people predict them.",
)


def _loading_message() -> str:
    """Select a short, local loading message without external calls."""
    return choice(LOADING_MESSAGES)


def limit_company_description(description: Any, max_sentences: int = 5) -> Any:
    """Keep a company description to complete sentences without splitting common abbreviations."""
    if not isinstance(description, str) or not description.strip():
        return description
    if max_sentences <= 0:
        return ""

    abbreviations = {
        "al", "approx", "co", "corp", "dr", "e.g", "etc", "i.e", "inc", "jr",
        "ltd", "mr", "mrs", "ms", "prof", "vs",
    }
    boundaries: list[int] = []
    for match in re.finditer(r"""[.!?]+(?:["'”’)]*)(?=\s+|$)""", description):
        preceding = description[:match.start() + 1]
        word_match = re.search(r"[\w.]+$", preceding)
        raw_word = word_match.group().lower() if word_match else ""
        word = raw_word.rstrip(".")
        is_initialism = bool(re.fullmatch(r"(?:[a-z]\.){2,}", raw_word))
        if match.end() != len(description) and (
            word in abbreviations
            or (len(word) == 1 and word.isalpha())
            or is_initialism
        ):
            continue
        boundaries.append(match.end())

    if len(boundaries) < max_sentences:
        return description
    if len(boundaries) == max_sentences:
        if not description[boundaries[-1]:].strip():
            return description
        return description[:boundaries[-1]].rstrip()
    return description[:boundaries[max_sentences - 1]].rstrip()


def _toggle_assessment_evidence(indicator_key: str) -> None:
    current = st.session_state.get("selected_evidence_indicator")
    st.session_state["selected_evidence_indicator"] = (
        None if current == indicator_key else indicator_key
    )


def _render_assessment_evidence(
    report: dict,
    card: dict[str, str],
    indicator_key: str,
) -> None:
    """Render selected indicator evidence at the page width below its card row."""
    evidence = assessment_display.get_indicator_evidence_display(
        report, indicator_key, card["name"]
    )
    with st.container(border=True):
        st.markdown(f"### {escape(card['name'])}")
        style = escape(card["style"])
        label = escape(card["label"])
        st.markdown(
            f'<span class="assessment-badge assessment-{style}">{label}</span>',
            unsafe_allow_html=True,
        )
        if card["driver"]:
            st.caption(card["driver"])
        st.markdown("**Supporting Evidence**")

        groups = dict.fromkeys(
            metric["group"] for metric in evidence["metrics"] if metric["group"]
        )
        for group in groups:
            st.markdown(f"**{escape(group)}**")
            rows = [
                {"Metric": metric["label"], "Value": metric["value"]}
                for metric in evidence["metrics"]
                if metric["group"] == group
            ]
            st.table(rows)

        for table in evidence["tables"]:
            st.markdown(f"**{escape(table['title'])}**")
            st.table(table["rows"])
        for paragraph in evidence["paragraphs"]:
            st.markdown(f"**{escape(paragraph['title'])}**")
            st.write(paragraph["text"])
        for section in evidence["bullets"]:
            st.markdown(f"**{escape(section['title'])}**")
            for bullet in section["items"]:
                st.markdown(f"- {bullet}")
        if not evidence["available"]:
            st.info("No supporting evidence is available for this indicator.")


def _render_assessment_card(container: Any, card: dict[str, str], indicator_key: str) -> None:
    style = escape(card["style"])
    label = escape(card["label"])
    driver = escape(card["driver"]) or " "
    container.markdown(
        f'<div class="assessment-card">'
        f'<div class="assessment-card-title">{escape(card["name"])}</div>'
        f'<div><span class="assessment-badge assessment-{style}">{label}</span></div>'
        f'<div class="assessment-card-driver">{driver}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    is_selected = st.session_state.get("selected_evidence_indicator") == indicator_key
    container.button(
        "Hide evidence" if is_selected else "View evidence",
        key=f"assessment-evidence-{indicator_key}",
        width="stretch",
        on_click=_toggle_assessment_evidence,
        args=(indicator_key,),
    )


def _render_loading_company(placeholder: Any, company: dict[str, Any]) -> None:
    description = company.get("description")
    loading_container = placeholder.container()
    with loading_container:
        if isinstance(description, str) and description.strip():
            name = company.get("name") or company.get("ticker") or "Company"
            loading_container.markdown(
                f"**{escape(str(name))}**\n\n"
                f'<div class="company-description">{escape(description.strip())}</div>',
                unsafe_allow_html=True,
            )
            loading_container.divider()
            loading_container.caption("While you wait")
        loading_container.caption(_loading_message())


def _build_report_for_ticker(ticker: str) -> None:
    LOGGER.info("Company lookup started: ticker=%s", ticker)
    with st.spinner(f"Checking {ticker}..."):
        try:
            company = main.get_company_info(ticker)
        except main.ReportBuildError as error:
            diagnostics.log_exception(LOGGER, "company_lookup", error)
            LOGGER.info("Company lookup failed: ticker=%s", ticker)
            st.error("Could not complete the analysis. Please try again.")
            return
        except Exception as error:
            diagnostics.log_exception(LOGGER, "company_lookup", error)
            raise

        if company is None:
            LOGGER.warning("Company lookup returned None: ticker=%s", ticker)
            LOGGER.info("User-facing error written: company_not_found")
            st.error("Ticker or company not found. Check the symbol or company name and try again.")
            return

        LOGGER.info(
            "Company lookup succeeded: ticker=%s company_name=%r",
            ticker,
            company.get("name"),
        )
        company_description = limit_company_description(company.get("description"))
        if "description" in company:
            company["description"] = company_description
        loading_placeholder = st.empty()
        _render_loading_company(loading_placeholder, company)
        LOGGER.info("Report build started: ticker=%s", ticker)
        try:
            report = main.build_report(ticker, preloaded_company=company)
        except main.ReportBuildError as error:
            diagnostics.log_exception(LOGGER, "report_build", error)
            LOGGER.info("Report build raised ReportBuildError: ticker=%s", ticker)
            LOGGER.info("User-facing error written: report_build_failed")
            st.error("Could not complete the analysis. Please try again.")
            return
        except Exception as error:
            diagnostics.log_exception(LOGGER, "report_build", error)
            raise
        finally:
            loading_placeholder.empty()

    LOGGER.info(
        "Report build returned: ticker=%s is_none=%s keys=%s",
        ticker,
        report is None,
        sorted(report.keys()) if isinstance(report, dict) else [],
    )
    if report is not None:
        st.session_state["research_report"] = report
        LOGGER.info("Session state report written: ticker=%s key=research_report", ticker)
    else:
        LOGGER.warning("Report build returned None: ticker=%s", ticker)
        LOGGER.info("User-facing error written: report_not_found")
        st.error("Ticker or company not found. Check the symbol or company name and try again.")


st.set_page_config(
    page_title="Stock Checker",
    page_icon="static/stock_checker_icon.png",
)
st.html(
    """
    <script>
    (() => {
      const headLinks = [
        ["manifest", "/app/static/stock_checker_manifest.json"],
        ["apple-touch-icon", "/app/static/stock_checker_icon.png"],
      ];
      for (const [rel, href] of headLinks) {
        let link = document.head.querySelector(`link[rel="${rel}"]`);
        if (!link) {
          link = document.createElement("link");
          link.rel = rel;
          document.head.appendChild(link);
        }
        link.href = href;
      }
    })();
    </script>
    """,
    unsafe_allow_javascript=True,
)
st.title("Stock Checker")
st.write("Research public companies with company, financial, and market context.")

ASSESSMENT_STYLES = """
<style>
.assessment-badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    border: 1px solid transparent;
}
.assessment-positive { color: #ffffff; background: #166534; border-color: #14532d; }
.assessment-neutral { color: #ffffff; background: #1e40af; border-color: #1e3a8a; }
.assessment-caution { color: #ffffff; background: #c2410c; border-color: #9a3412; }
.assessment-muted { color: #ffffff; background: #4b5563; border-color: #374151; }
.assessment-card {
    box-sizing: border-box;
    height: 190px;
    padding: 0.9rem;
    border: 1px solid #64748b;
    border-radius: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
}
.assessment-card-title {
    font-size: 1rem;
    font-weight: 650;
    line-height: 1.25;
    min-height: 2.5rem;
    overflow-wrap: anywhere;
}
.assessment-card-driver {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-wrap: anywhere;
    line-height: 1.35;
}
.company-description {
    margin: 0.35rem 0 1rem;
}
</style>
"""

with st.form("ticker_analysis_form"):
    ticker = st.text_input("Ticker", placeholder="e.g. AAPL").strip()
    submitted = st.form_submit_button("Analyse")

if submitted:
    LOGGER.info(
        "Analysis submitted: input=%r layout_mode=%s",
        ticker,
        st.session_state.get("assessment_layout_mode", "Desktop"),
    )
    LOGGER.info(
        "Provider API key presence: GOOGLE_API_KEY=%s TAVILY_API_KEY=%s MARKETAUX_API_KEY=%s",
        *(bool(os.environ.get(name)) for name in PROVIDER_API_KEY_NAMES),
    )
    st.session_state.pop("research_report", None)
    st.session_state.pop("selected_evidence_indicator", None)
    st.session_state.pop("ticker_resolution_candidates", None)
    if not ticker:
        LOGGER.info("User-facing error written: empty_ticker")
        st.error("Please enter a ticker symbol.")
    else:
        LOGGER.info("Ticker resolution started: input=%r", ticker)
        try:
            resolution = ticker_resolution.resolve_security_input(ticker)
        except ticker_resolution.TickerResolutionError as error:
            diagnostics.log_exception(LOGGER, "ticker_resolution", error)
            LOGGER.info("User-facing error written: ticker_resolution_failed")
            st.error("Could not look up that ticker or company right now. Please try again.")
        except Exception as error:
            diagnostics.log_exception(LOGGER, "ticker_resolution", error)
            raise
        else:
            LOGGER.info(
                "Ticker resolution returned: status=%s canonical_ticker=%s candidate_count=%s",
                resolution.status,
                resolution.ticker if resolution.status == "resolved" else None,
                len(resolution.candidates) if resolution.status == "ambiguous" else 0,
            )
            if resolution.status == "resolved" and resolution.ticker:
                _build_report_for_ticker(resolution.ticker)
            elif resolution.status == "ambiguous":
                st.session_state["ticker_resolution_candidates"] = resolution.candidates
                LOGGER.info(
                    "Session state candidates written: candidate_count=%d",
                    len(resolution.candidates),
                )
            else:
                LOGGER.info("Ticker resolution not_found: input=%r", ticker)
                LOGGER.info("User-facing error written: ticker_not_found")
                st.error("Ticker or company not found. Check the symbol or company name and try again.")

pending_candidates = st.session_state.get("ticker_resolution_candidates")
if pending_candidates:
    selected_candidate = st.selectbox(
        "Choose a listing",
        options=pending_candidates,
        format_func=lambda candidate: " — ".join(
            part for part in (
                candidate.ticker,
                candidate.company_name,
                candidate.exchange,
            ) if part
        ),
        key="ticker-resolution-selection",
    )
    if st.button("Analyse selected listing", key="analyse-selected-listing"):
        LOGGER.info(
            "Ambiguous listing selected: ticker=%s company_name=%r",
            selected_candidate.ticker,
            selected_candidate.company_name,
        )
        st.session_state.pop("ticker_resolution_candidates", None)
        _build_report_for_ticker(selected_candidate.ticker)

report = st.session_state.get("research_report")
if isinstance(report, dict):
    company = report.get("company") if isinstance(report.get("company"), dict) else {}
    name = company.get("name") or "Company"
    symbol = report.get("ticker") or ""
    st.subheader(f"{name} ({symbol})")
    header_columns = st.columns(2)
    header_columns[0].metric("Share Price", display.format_price(company.get("price")))
    header_columns[1].metric("Market Cap", display.format_market_cap(company.get("market_cap")))
    description = company.get("description")
    if isinstance(description, str) and description.strip():
        st.markdown(
            f'<div class="company-description">{escape(description.strip())}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(ASSESSMENT_STYLES, unsafe_allow_html=True)
    st.subheader("Stock Assessment")
    st.session_state.setdefault("assessment_layout_mode", "Desktop")
    st.segmented_control(
        "Layout",
        options=("Desktop", "Mobile"),
        key="assessment_layout_mode",
        width="content",
    )
    assessment_cards = assessment_display.get_assessment_display(report)
    indicator_specs = assessment_display.ASSESSMENT_INDICATORS
    selected_indicator = st.session_state.get("selected_evidence_indicator")
    if st.session_state["assessment_layout_mode"] == "Mobile":
        for card, (indicator_key, _) in zip(assessment_cards, indicator_specs):
            _render_assessment_card(st, card, indicator_key)
            if selected_indicator == indicator_key:
                _render_assessment_evidence(report, card, indicator_key)
    else:
        for start in range(0, len(assessment_cards), 4):
            columns = st.columns(4)
            for column, card, (indicator_key, _) in zip(
                columns,
                assessment_cards[start : start + 4],
                indicator_specs[start : start + 4],
            ):
                _render_assessment_card(column, card, indicator_key)

            selected_index = next(
                (
                    index for index, (key, _) in enumerate(indicator_specs)
                    if key == selected_indicator
                ),
                None,
            )
            if selected_index is not None and start <= selected_index < start + 4:
                _render_assessment_evidence(
                    report,
                    assessment_cards[selected_index],
                    indicator_specs[selected_index][0],
                )

    qualitative_sections = (
        ("AI Company Analysis", qualitative_display.get_company_analysis_display(report)),
        ("Market & Industry Review", qualitative_display.get_market_review_display(report)),
        ("Bull / Bear Scenario Analysis", qualitative_display.get_bull_bear_display(report)),
    )
    for title, section in qualitative_sections:
        with st.expander(title, expanded=False):
            if not section["available"]:
                st.info(section["message"])
                continue

            for item in section["sections"]:
                st.markdown(f"**{item['title']}**")
                if item["kind"] == "text":
                    st.write(item["content"])
                else:
                    for bullet in item["content"]:
                        st.markdown(f"- {bullet}")

            if title == "Market & Industry Review" and section["sources"]:
                st.markdown("**Sources**")
                for source in section["sources"]:
                    if source["url"] and source["title"]:
                        st.markdown(f"[{source['title']}]({source['url']})")
                    elif source["title"]:
                        st.write(source["title"])
                    details = [
                        value for value in (source["source"], source["published_at"]) if value
                    ]
                    if details:
                        st.caption(" · ".join(details))
