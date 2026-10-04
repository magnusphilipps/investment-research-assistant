"""Streamlit entry point for the stock assessment dashboard."""

from html import escape

from dotenv import load_dotenv
import streamlit as st

load_dotenv(".env")

from investment_research import assessment_display, display, main, qualitative_display


st.set_page_config(page_title="Investment Research Assistant")
st.title("Investment Research Assistant")
st.write("Research public companies using the existing analysis pipeline.")

ASSESSMENT_STYLES = """
<style>
.assessment-badge {
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
}
.assessment-positive { color: #1b5e20; background: #e8f5e9; }
.assessment-neutral { color: #34495e; background: #eef2f6; }
.assessment-caution { color: #8a3b12; background: #fff3e0; }
.assessment-muted { color: #65717c; background: #f1f3f5; }
</style>
"""

with st.form("ticker_analysis_form"):
    ticker = st.text_input("Ticker", placeholder="e.g. AAPL").strip().upper()
    submitted = st.form_submit_button("Analyse")

if submitted:
    st.session_state.pop("research_report", None)
    if not ticker:
        st.error("Please enter a ticker symbol.")
    else:
        report = None
        build_failed = False
        with st.spinner(f"Analysing {ticker}..."):
            try:
                report = main.build_report(ticker)
            except main.ReportBuildError:
                build_failed = True
                st.error("Could not complete the analysis. Please try again.")
            if report is None and not build_failed:
                st.error("Ticker not found. Check the symbol and try again.")
            elif report is not None:
                st.session_state["research_report"] = report

report = st.session_state.get("research_report")
if isinstance(report, dict):
    company = report.get("company") if isinstance(report.get("company"), dict) else {}
    name = company.get("name") or "Company"
    symbol = report.get("ticker") or ""
    st.subheader(f"{name} ({symbol})")
    header_columns = st.columns(2)
    header_columns[0].metric("Share Price", display.format_price(company.get("price")))
    header_columns[1].metric("Market Cap", display.format_market_cap(company.get("market_cap")))

    st.markdown(ASSESSMENT_STYLES, unsafe_allow_html=True)
    st.subheader("Stock Assessment")
    assessment_cards = assessment_display.get_assessment_display(report)
    for start in range(0, len(assessment_cards), 4):
        columns = st.columns(4)
        for column, card in zip(columns, assessment_cards[start : start + 4]):
            with column.container(border=True):
                st.markdown(f"**{escape(card['name'])}**")
                style = escape(card["style"])
                label = escape(card["label"])
                st.markdown(
                    f'<span class="assessment-badge assessment-{style}">{label}</span>',
                    unsafe_allow_html=True,
                )
                if card["driver"]:
                    st.caption(card["driver"])

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
