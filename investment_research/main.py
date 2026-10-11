"""Application orchestration shared by the terminal and Streamlit interfaces."""

from __future__ import annotations

import logging
from typing import Any

from . import assessment
from . import analysis
from . import display
from . import expectations
from . import fetcher
from . import financials
from . import market_research
from . import news
from . import peers
from . import performance
from . import diagnostics

LOGGER = logging.getLogger(__name__)


class ReportBuildError(Exception):
    """Raised when required company or financial data prevents report creation."""


def get_company_info(ticker: str) -> dict[str, Any] | None:
    """Fetch the existing company overview once, with report-level error handling."""
    symbol = ticker.strip().upper()
    if not symbol:
        LOGGER.warning("Company lookup skipped: empty ticker")
        return None
    try:
        company = fetcher.get_stock_info(symbol)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "company_lookup_provider", error)
        raise ReportBuildError(f"Could not retrieve data: {error}") from error
    if company is None:
        LOGGER.warning("Company lookup provider returned None: ticker=%s", symbol)
    return company


def build_report(
    ticker: str,
    *,
    preloaded_company: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run the existing analysis pipeline once and return its structured results.

    Returns None when the ticker does not resolve to a public security. Optional
    providers are isolated and represented by their usual unavailable result.
    """
    symbol = ticker.strip().upper()
    if not symbol:
        LOGGER.warning("Report build skipped: empty ticker")
        return None

    company = preloaded_company if preloaded_company is not None else get_company_info(symbol)
    if company is None:
        LOGGER.warning("Report build stopped: company lookup returned None ticker=%s", symbol)
        return None

    try:
        statements = financials.get_financial_statements(symbol)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "financial_statements", error)
        raise ReportBuildError(f"Could not retrieve financial statements: {error}") from error
    if statements is None:
        LOGGER.warning("Financial statements returned None: ticker=%s", symbol)
        raise ReportBuildError("Financial statement data unavailable for this ticker.")

    errors: dict[str, str] = {}
    try:
        ratios = financials.get_ratios(symbol, statements)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "ratios", error)
        ratios = {}
        errors["ratios"] = f"Could not compute financial ratios: {error}"

    peer_result = {
        "available": False,
        "message": "Peer comparison unavailable for this company.",
    }
    try:
        peer_result = peers.fetch_peer_comparison(symbol)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "peer_comparison", error)
        errors["peers"] = f"Could not retrieve peer comparison: {error}"
    if isinstance(peer_result, dict) and peer_result.get("available") is False:
        LOGGER.warning("Peer comparison unavailable: ticker=%s", symbol)

    try:
        price_performance = performance.get_performance(
            symbol,
            exchange=company.get("exchange"),
            market=company.get("market"),
        )
    except Exception as error:
        diagnostics.log_exception(LOGGER, "price_performance", error)
        price_performance = None
        errors["price_performance"] = f"Could not retrieve stock price performance: {error}"
    if price_performance is None and "price_performance" not in errors:
        LOGGER.warning("Price performance returned None: ticker=%s", symbol)
        errors["price_performance"] = "Stock price performance data unavailable for this ticker."

    expectations_data = {}
    try:
        income = statements.get("income")
        revenue_stage = income.get("revenue_stage") if isinstance(income, dict) else None
        expectations_data = expectations.get_analyst_expectations(
            symbol,
            revenue_stage=revenue_stage,
        )
    except Exception as error:
        diagnostics.log_exception(LOGGER, "analyst_expectations", error)
        errors["expectations"] = f"Could not retrieve analyst expectations: {error}"

    try:
        news_result = news.get_company_news(symbol)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "company_news", error)
        news_result = {
            "status": "unavailable",
            "message": "Recent news temporarily unavailable.",
            "articles": [],
        }
    if isinstance(news_result, dict) and news_result.get("status") == "unavailable":
        LOGGER.warning("Company news unavailable: ticker=%s", symbol)

    analysis_context = analysis.build_analysis_context(
        ticker=symbol,
        stock_info=company,
        financials=statements,
        ratios=ratios,
        performance=price_performance,
        expectations=expectations_data,
        peers=peer_result,
        news=news_result,
    )
    try:
        company_analysis = analysis.get_ai_analysis(analysis_context)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "company_analysis", error)
        company_analysis = {
            "status": "unavailable",
            "message": "AI analysis temporarily unavailable.",
            "analysis": None,
        }
    if isinstance(company_analysis, dict) and company_analysis.get("status") == "unavailable":
        LOGGER.warning("Company analysis unavailable: ticker=%s", symbol)

    try:
        market_review = market_research.get_market_review(company)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "market_review", error)
        market_review = {
            "status": "unavailable",
            "message": "Market & industry review temporarily unavailable.",
            "review": None,
            "sources": [],
        }
    if isinstance(market_review, dict) and market_review.get("status") == "unavailable":
        LOGGER.warning("Market review unavailable: ticker=%s", symbol)

    bull_bear_context = analysis.build_bull_bear_context(analysis_context, market_review)
    try:
        bull_bear = analysis.get_bull_bear_analysis(bull_bear_context)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "bull_bear_analysis", error)
        bull_bear = {
            "status": "unavailable",
            "message": "Bull / Bear analysis temporarily unavailable.",
            "analysis": None,
        }
    if isinstance(bull_bear, dict) and bull_bear.get("status") == "unavailable":
        LOGGER.warning("Bull / Bear analysis unavailable: ticker=%s", symbol)

    assessment_context = {
        "ticker": symbol,
        "company": company,
        "financials": statements,
        "ratios": ratios,
        "performance": price_performance,
        "analyst_expectations": expectations_data,
        "peer_comparison": peer_result,
        "valuation": ratios.get("valuation", {}) if isinstance(ratios, dict) else {},
        "company_analysis": company_analysis,
        "market_review": market_review,
    }
    try:
        stock_assessment = assessment.build_stock_assessment(assessment_context)
    except Exception as error:
        diagnostics.log_exception(LOGGER, "stock_assessment", error)
        errors["assessment"] = f"Could not build stock assessment: {error}"
        stock_assessment = {"status": "ok", "indicators": {}}
    if isinstance(stock_assessment, dict) and stock_assessment.get("status") == "unavailable":
        LOGGER.warning("Stock assessment unavailable: ticker=%s", symbol)

    return {
        "ticker": symbol,
        "company": company,
        "financials": statements,
        "ratios": ratios,
        "peers": peer_result,
        "price_performance": price_performance,
        "expectations": expectations_data,
        "news": news_result,
        "company_analysis": company_analysis,
        "market_review": market_review,
        "bull_bear": bull_bear,
        "assessment": stock_assessment,
        "errors": errors,
    }


def render_terminal_report(report: dict[str, Any]) -> None:
    """Render a structured report using the existing terminal formatters."""
    company = report["company"]
    statements = report["financials"]
    errors = report.get("errors", {})

    display.print_stock_info(company)
    display.print_company_overview(company)
    display.print_income_statement(statements)
    display.print_balance_sheet(statements)
    display.print_cash_flow(statements)

    if "ratios" in errors:
        display.print_error(errors["ratios"])
    else:
        display.print_ratios(report["ratios"], statements)

    if "peers" in errors:
        display.print_error(errors["peers"])
    else:
        display.print_peer_comparison(report["peers"])

    if "price_performance" in errors:
        display.print_error(errors["price_performance"])
    else:
        display.print_performance(report["price_performance"])

    if "expectations" in errors:
        display.print_error(errors["expectations"])
    else:
        display.print_analyst_expectations(report["expectations"])

    display.print_news(report["news"])
    display.print_ai_analysis(report["company_analysis"])
    display.print_market_review(report["market_review"], company.get("name") or report["ticker"])
    display.print_bull_bear_analysis(report["bull_bear"])
    if "assessment" in errors:
        display.print_error(errors["assessment"])
    display.print_stock_assessment(report["assessment"])


def run() -> None:
    """Run the interactive terminal workflow using the shared report pipeline."""
    display.print_welcome()
    while True:
        ticker = input("  Enter ticker symbol: ").strip().upper()
        if not ticker:
            display.print_error("Please enter a ticker symbol.")
            continue
        if ticker in ("QUIT", "Q"):
            print("\n  Goodbye!\n")
            break

        print(f"\n  Looking up {ticker}...")
        try:
            report = build_report(ticker)
        except ReportBuildError as error:
            display.print_error(str(error))
            continue
        if report is None:
            display.print_error("Ticker not found. Check the symbol and try again.")
            continue
        render_terminal_report(report)
