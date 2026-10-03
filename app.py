"""Minimal Streamlit entry point for the structured research report."""

from dotenv import load_dotenv
import streamlit as st

load_dotenv(".env")

from investment_research import display, main


st.set_page_config(page_title="Investment Research Assistant")
st.title("Investment Research Assistant")
st.write("Research public companies using the existing analysis pipeline.")

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
    st.write(f"Share Price: {display.format_price(company.get('price'))}")
    st.write(f"Market Cap: {display.format_market_cap(company.get('market_cap'))}")
    st.success("Analysis loaded successfully.")
    st.caption("Development check — report data available:")
    st.write([key for key in report if key != "errors"])
