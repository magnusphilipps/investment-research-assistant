# ============================================================
# display.py — Output Formatting
# ============================================================
#
# PURPOSE:
#   This module handles everything related to how information
#   is shown to the user in the terminal.
#
#   Separating "display" code from "data" code is a core
#   principle called Separation of Concerns. It means:
#     - fetcher.py    →  knows HOW to get data
#     - financials.py →  knows HOW to calculate financial figures
#     - display.py    →  knows HOW to show data
#     - main.py       →  coordinates all three
#
#   This makes each file easier to read, test, and change.
#
# PHASES:
#   Phase 1: format_market_cap(), print_stock_info()
#   Phase 2: format_employees(), print_company_overview()
#   Phase 3: format_financial_value(), format_percent(),
#             format_growth(), format_eps(), format_shares(),
#             print_income_statement(), print_balance_sheet(),
#             print_cash_flow()
# ============================================================

# textwrap is part of Python's standard library — no installation needed.
# It provides utilities for wrapping and filling text to a fixed width,
# which is useful when printing long paragraphs in a terminal.
import textwrap

# ---- Layout constants for Phase 3 financial tables ----------
# Keeping these as module-level constants means you only need to
# change one number to reformat every financial table at once.
_LABEL_WIDTH = 24   # characters reserved for the row label column
_COL_WIDTH   = 12   # characters per year column (right-aligned values)


def format_market_cap(market_cap: int | None) -> str:
    """
    Convert a raw market cap number into a human-readable string.

    For example:
        2_800_000_000_000  →  "$2.80 Trillion"
        500_000_000        →  "$500.00 Million"

    Parameters:
        market_cap: The raw integer value (or None if unavailable)

    Returns:
        A formatted string.
    """

    # If the data is missing, return a friendly placeholder.
    if market_cap is None:
        return "N/A"

    # We use "elif" (else-if) to check thresholds from largest to smallest.
    if market_cap >= 1_000_000_000_000:          # 1 trillion
        value = market_cap / 1_000_000_000_000
        return f"${value:,.2f} Trillion"

    elif market_cap >= 1_000_000_000:            # 1 billion
        value = market_cap / 1_000_000_000
        return f"${value:,.2f} Billion"

    elif market_cap >= 1_000_000:                # 1 million
        value = market_cap / 1_000_000
        return f"${value:,.2f} Million"

    else:
        # Format with commas: 1234567 → $1,234,567
        return f"${market_cap:,}"


def print_stock_info(data: dict) -> None:
    """
    Print a formatted summary of a stock to the terminal.

    Parameters:
        data (dict): The dictionary returned by fetcher.get_stock_info()
    """

    # A separator line makes the output easier to read at a glance.
    separator = "-" * 40

    print()          # Blank line for visual breathing room
    print(separator)
    print(f"  {data['name']} ({data['ticker']})")
    print(separator)

    # Format the share price. If it's missing, show "N/A".
    if data["price"] is not None:
        print(f"  Share Price  :  ${data['price']:,.2f}")
    else:
        print(f"  Share Price  :  N/A")

    # format_market_cap handles None internally, so we can call it directly.
    market_cap_str = format_market_cap(data["market_cap"])
    print(f"  Market Cap   :  {market_cap_str}")

    print(separator)
    print()          # Trailing blank line


def format_employees(employees: int | None) -> str:
    """
    Convert a raw employee headcount into a human-readable string.

    For example:
        161000  →  "161,000"
        None    →  "N/A"

    The :, format specifier tells Python to insert commas as
    thousands separators. It is the same specifier used for
    market cap numbers elsewhere in this file.

    Parameters:
        employees: The raw integer from yfinance, or None.

    Returns:
        A formatted string.
    """
    if employees is None:
        return "N/A"

    # f"{value:,}" formats an integer with comma separators.
    # Example: f"{161000:,}"  →  "161,000"
    return f"{employees:,}"


def print_company_overview(data: dict) -> None:
    """
    Print the Phase 2 company overview block to the terminal.

    This function is called immediately after print_stock_info()
    in main.py. It receives the same `data` dictionary and reads
    only the Phase 2 keys that belong to it.

    Parameters:
        data (dict): The dictionary returned by fetcher.get_stock_info()
    """

    separator = "-" * 40

    # --- Section header ---
    print(f"  COMPANY OVERVIEW")
    print(separator)

    # or is used as a fallback here: if data.get("sector") returns
    # None (field was missing), the expression evaluates to "N/A".
    # This is called a "short-circuit" — Python stops evaluating
    # as soon as it finds a truthy value.
    print(f"  Sector       :  {data.get('sector')     or 'N/A'}")
    print(f"  Industry     :  {data.get('industry')   or 'N/A'}")
    print(f"  Country      :  {data.get('country')    or 'N/A'}")
    print(f"  Employees    :  {format_employees(data.get('employees'))}")
    print(f"  Website      :  {data.get('website')    or 'N/A'}")

    print(separator)

    # --- Business description ---
    # Business descriptions from Yahoo Finance are often several hundred
    # words long. Printing them as one unbroken line is hard to read.
    # textwrap.fill() wraps a long string to a maximum line width and
    # returns it as a single string with newline characters inserted.
    #
    # textwrap.fill(text, width, initial_indent, subsequent_indent):
    #   - width             : maximum characters per line
    #   - initial_indent    : prefix added to the very first line
    #   - subsequent_indent : prefix added to every line after the first
    #
    # Both indents use two spaces so the text aligns with the fields above.
    description = data.get("description")

    if description:
        wrapped = textwrap.fill(
            description,
            width=70,
            initial_indent="  ",
            subsequent_indent="  ",
        )
        print(wrapped)
    else:
        print("  No description available.")

    print(separator)
    print()  # Trailing blank line


# ============================================================
# Phase 3 — Financial Statement Formatters and Printers
# ============================================================

def format_financial_value(value: float | None, symbol: str = "$") -> str:
    """
    Format a raw financial figure into a compact, readable string.

    Uses T/B/M/K suffixes so large numbers fit neatly into table columns.

    Examples (with symbol="$"):
        391_000_000_000  →  "$391.0B"
         -8_700_000      →  "-$8.7M"
               1_234     →  "$1.2K"
                None     →  "N/A"

    Parameters:
        value  : Raw float from financials.py, or None.
        symbol : Currency symbol prefix (e.g. "$", "£", "€").

    Returns:
        A compact formatted string.
    """
    if value is None:
        return "N/A"

    # Handle negative values: extract the sign separately so we can
    # place it before the currency symbol, e.g. "-$8.7M" not "$-8.7M".
    sign    = "-" if value < 0 else ""
    abs_val = abs(value)

    if abs_val >= 1e12:
        return f"{sign}{symbol}{abs_val / 1e12:.1f}T"
    elif abs_val >= 1e9:
        return f"{sign}{symbol}{abs_val / 1e9:.1f}B"
    elif abs_val >= 1e6:
        return f"{sign}{symbol}{abs_val / 1e6:.1f}M"
    elif abs_val >= 1e3:
        return f"{sign}{symbol}{abs_val / 1e3:.1f}K"
    else:
        return f"{sign}{symbol}{abs_val:.2f}"


def format_percent(value: float | None) -> str:
    """
    Format a percentage value (e.g. a margin) to one decimal place.

    The value is expected as a plain percentage, not a fraction —
    so 46.2 means 46.2%, not 0.462.

    Examples:
        46.2   →  "46.2%"
        -3.1   →  "-3.1%"
        None   →  "N/A"
    """
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def format_growth(value: float | None) -> str:
    """
    Format a revenue growth percentage with an explicit +/- sign.

    The explicit sign makes it immediately clear whether growth is
    positive or negative — important when several years are shown
    side by side.

    Examples:
         2.04  →  "+2.0%"
        -2.80  →  "-2.8%"
         None  →  "N/A"
    """
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def format_margin_change(value: float | None) -> str:
    """
    Format a year-on-year margin change in percentage points (pp).

    Margin changes are measured in percentage POINTS, not percentage
    growth.  A gross margin moving from 44.1% to 46.2% is a change
    of +2.1 pp — not +4.8% (which would be the percentage change of
    the margin itself, a different and less intuitive figure).

    Examples:
         0.7  →  "+0.7 pp"
        -1.2  →  "-1.2 pp"
        None  →  "N/A"
    """
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f} pp"


def _margin_direction(yoy: float | None) -> str:
    """
    Convert a YoY margin change (in pp) to a plain-English direction word.

    Used to build rule-based summary sentences.  A threshold of ±0.2 pp
    avoids labelling rounding-level noise as a meaningful movement.

    Returns one of: "improved", "declined", "broadly stable", or ""
    (empty string when data is unavailable, so the caller can skip it).
    """
    if yoy is None:
        return ""
    if yoy > 0.2:
        return "improved"
    elif yoy < -0.2:
        return "declined"
    else:
        return "broadly stable"


def format_eps(value: float | None, symbol: str = "$") -> str:
    """
    Format an earnings-per-share value to two decimal places.

    EPS is a small per-share number (e.g. 6.08) so we do not apply
    the B/M/K suffixes — two decimal places is sufficient precision.

    Examples:
        6.08   →  "$6.08"
        -1.25  →  "-$1.25"
        None   →  "N/A"
    """
    if value is None:
        return "N/A"
    sign    = "-" if value < 0 else ""
    abs_val = abs(value)
    return f"{sign}{symbol}{abs_val:.2f}"


def format_shares(value: float | None) -> str:
    """
    Format a share count (diluted average shares outstanding).

    Share counts are large raw integers (e.g. 15_410_000_000) so
    we apply B/M suffixes for readability.  No currency symbol is
    used — shares are a count, not a monetary amount.

    Examples:
        15_410_000_000  →  "15.41B"
           800_000_000  →  "800.0M"
                  None  →  "N/A"
    """
    if value is None:
        return "N/A"
    abs_val = abs(value)
    if abs_val >= 1e9:
        return f"{value / 1e9:.2f}B"
    elif abs_val >= 1e6:
        return f"{value / 1e6:.1f}M"
    return f"{value:,.0f}"


def _table_row(label: str, cells: list[str]) -> str:
    """
    Build one row of a multi-column financial table.

    The label is left-aligned in _LABEL_WIDTH characters.
    Each cell value is right-aligned in _COL_WIDTH characters.
    This produces columns that line up neatly regardless of
    how long the formatted values are.

    Example output (with _LABEL_WIDTH=24, _COL_WIDTH=12):
        "  Revenue                   $391.0B     $383.3B     $394.3B"

    Parameters:
        label : Row description, e.g. "Revenue"
        cells : List of formatted string values, one per year column.
    """
    # f"  {label:<{_LABEL_WIDTH}}" left-pads the label to exactly
    # _LABEL_WIDTH characters, preceded by two spaces for indentation.
    label_str  = f"  {label:<{_LABEL_WIDTH}}"
    # f"{cell:>{_COL_WIDTH}}" right-aligns each cell value.
    cells_str  = "".join(f"{cell:>{_COL_WIDTH}}" for cell in cells)
    return label_str + cells_str


def print_income_statement(fin: dict) -> None:
    """
    Print the income statement section of the financial report.

    Displays up to four annual periods in a side-by-side table:
      - Revenue and revenue growth (with acceleration label)
      - Gross profit and gross margin
      - Operating income and operating margin
      - Net income
      - EPS (diluted where available; basic otherwise)
      - Diluted average shares (so the user can judge buyback effects)

    Parameters:
        fin (dict): The dictionary returned by
                    financials.get_financial_statements().
    """
    inc    = fin.get("income", {})
    sym    = fin.get("currency_symbol", "$")
    code   = fin.get("currency_code", "USD")
    sep    = "-" * (2 + _LABEL_WIDTH + _COL_WIDTH * 3)

    print()
    print(f"  INCOME STATEMENT  (Annual · {code})")
    print(sep)

    # If the income statement was not available, show a single message.
    if "error" in inc:
        print(f"  {inc['error']}")
        print(sep)
        print()
        return

    years = inc.get("years", [])
    if not years:
        print("  No annual income statement data available.")
        print(sep)
        print()
        return

    n = len(years)

    # ---- Header row: year labels --------------------------------
    # Display years as "FY2024" to make it clear these are fiscal years.
    year_headers = [f"FY{y}" for y in years]
    print(_table_row("", year_headers))
    print(sep)

    # ---- Revenue ------------------------------------------------
    rev_cells = [
        format_financial_value(inc["revenue"][i], sym) for i in range(n)
    ]
    print(_table_row("Revenue", rev_cells))

    # Revenue growth: growth[i] = growth achieved in year[i].
    # The oldest available year has no prior year to compare, so it
    # shows "N/A".  We fill from revenue_growth, padding with None.
    rg = inc.get("revenue_growth", [])
    growth_cells = []
    for i in range(n):
        growth_cells.append(format_growth(rg[i]) if i < len(rg) else "N/A")
    print(_table_row("  Revenue Growth", growth_cells))

    # Revenue Growth Trend spans all columns — it is a single conclusion
    # about the direction of growth, not a per-year value.
    accel = inc.get("acceleration", "Unavailable")
    print(f"  {'  Revenue Growth Trend':<{_LABEL_WIDTH}}  {accel}")
    print(sep)

    # ---- YoY margin changes (computed once, used in table + summary) ----
    # Percentage point change = latest margin − prior year margin.
    # We compute these before the gross profit block so the same values
    # can be reused in the summary sentence below the table.
    gm_list = inc.get("gross_margin", [])
    om_list = inc.get("op_margin",    [])

    yoy_gm = (
        gm_list[0] - gm_list[1]
        if len(gm_list) >= 2 and gm_list[0] is not None and gm_list[1] is not None
        else None
    )
    yoy_om = (
        om_list[0] - om_list[1]
        if len(om_list) >= 2 and om_list[0] is not None and om_list[1] is not None
        else None
    )

    # ---- Gross profit -------------------------------------------
    gp_cells = [
        format_financial_value(inc["gross_profit"][i], sym) for i in range(n)
    ]
    print(_table_row("Gross Profit", gp_cells))

    gm_cells = [format_percent(gm_list[i]) for i in range(n)]
    print(_table_row("  Gross Margin", gm_cells))

    # YoY change: only the most recent year has a comparison period,
    # so we fill the remaining columns with empty strings.
    gm_yoy_cells = [format_margin_change(yoy_gm)] + [""] * (n - 1)
    print(_table_row("    YoY Change", gm_yoy_cells))
    print(sep)

    # ---- Operating income ---------------------------------------
    op_cells = [
        format_financial_value(inc["op_income"][i], sym) for i in range(n)
    ]
    print(_table_row("Operating Income", op_cells))

    om_cells = [format_percent(om_list[i]) for i in range(n)]
    print(_table_row("  Operating Margin", om_cells))

    om_yoy_cells = [format_margin_change(yoy_om)] + [""] * (n - 1)
    print(_table_row("    YoY Change", om_yoy_cells))
    print(sep)

    # ---- Net income, EPS, shares --------------------------------
    ni_cells = [
        format_financial_value(inc["net_income"][i], sym) for i in range(n)
    ]
    print(_table_row("Net Income", ni_cells))

    eps_cells = [format_eps(inc["eps_diluted"][i], sym) for i in range(n)]
    print(_table_row("EPS (Diluted)", eps_cells))

    sh_cells = [format_shares(inc["shares_diluted"][i]) for i in range(n)]
    print(_table_row("Shares (Diluted)", sh_cells))

    print(sep)

    # ---- Rule-based summary -------------------------------------
    # Built entirely from the data already computed above.
    # No qualitative judgements — only factual statements about direction.
    summary_parts = []

    # Revenue growth trend sentence
    if accel == "Accelerating":
        summary_parts.append("Revenue growth is accelerating.")
    elif accel == "Slowing":
        summary_parts.append("Revenue growth is slowing.")
    elif accel == "Broadly stable":
        summary_parts.append("Revenue growth is broadly stable.")
    # "Unavailable" → omit rather than print a confusing sentence

    # Margin direction sentence
    # _margin_direction() returns "improved", "declined", "broadly stable",
    # or "" (empty string) when the value is None.
    gm_dir = _margin_direction(yoy_gm)
    om_dir = _margin_direction(yoy_om)

    if gm_dir and om_dir:
        if gm_dir == om_dir:
            # Both moved in the same direction — combine into one sentence.
            summary_parts.append(
                f"Gross and operating margins both {gm_dir} "
                f"compared with the previous year."
            )
        else:
            summary_parts.append(
                f"Gross margin {gm_dir} and operating margin {om_dir} "
                f"compared with the previous year."
            )
    elif gm_dir:
        summary_parts.append(
            f"Gross margin {gm_dir} compared with the previous year."
        )
    elif om_dir:
        summary_parts.append(
            f"Operating margin {om_dir} compared with the previous year."
        )

    if summary_parts:
        summary_text = " ".join(summary_parts)
        print(textwrap.fill(
            summary_text,
            width=70,
            initial_indent="  ",
            subsequent_indent="  ",
        ))
        print()
    else:
        print()


def print_balance_sheet(fin: dict) -> None:
    """
    Print the balance sheet section (most recent annual period).

    Displays:
      - Liquidity : Cash, Total Debt, Shareholders Equity, D/E ratio
      - Short-term: Current Assets, Current Liabilities, Current Ratio
      - Equity    : Retained Earnings

    The D/E ratio is suppressed with an explanation when equity is
    zero or negative, to avoid misleading the user.

    Parameters:
        fin (dict): The dictionary returned by
                    financials.get_financial_statements().
    """
    bal = fin.get("balance", {})
    sym = fin.get("currency_symbol", "$")
    code = fin.get("currency_code", "USD")
    sep  = "-" * 42

    print()
    print(f"  BALANCE SHEET  (Most Recent Annual · {code})")
    print(sep)

    if "error" in bal:
        print(f"  {bal['error']}")
        print(sep)
        print()
        return

    def _line(label: str, value: str) -> None:
        """Print one labelled value row, left/right aligned."""
        print(f"  {label:<26}{value:>12}")

    # ---- Liquidity block ----------------------------------------
    _line("Cash & Equivalents",  format_financial_value(bal["cash"],       sym))
    _line("Total Debt",           format_financial_value(bal["total_debt"], sym))
    _line("Shareholders Equity",  format_financial_value(bal["equity"],     sym))

    # Debt-to-equity: show ratio if valid, otherwise the note.
    if bal["de_ratio"] is not None:
        _line("Debt / Equity Ratio", f"{bal['de_ratio']:.2f}x")
    else:
        _line("Debt / Equity Ratio", bal["de_note"] or "N/A")

    print(sep)

    # ---- Short-term solvency block ------------------------------
    _line("Current Assets",      format_financial_value(bal["current_assets"],       sym))
    _line("Current Liabilities", format_financial_value(bal["current_liabilities"],  sym))

    if bal["current_ratio"] is not None:
        _line("Current Ratio", f"{bal['current_ratio']:.2f}x")
    else:
        _line("Current Ratio", "N/A")

    print(sep)

    # ---- Retained earnings --------------------------------------
    _line("Retained Earnings",   format_financial_value(bal["retained_earnings"], sym))

    print(sep)

    # ---- Rule-based summary -------------------------------------
    # States the key facts without making any safety or risk judgement.
    summary_parts = []

    cash_str = format_financial_value(bal.get("cash"),       sym)
    debt_str = format_financial_value(bal.get("total_debt"), sym)

    if bal.get("cash") is not None or bal.get("total_debt") is not None:
        cash_clause = f"{cash_str} in cash" if bal.get("cash") is not None else "an undisclosed cash position"
        debt_clause = f"{debt_str} of debt" if bal.get("total_debt") is not None else "an undisclosed debt level"
        summary_parts.append(f"The company holds {cash_clause} against {debt_clause}.")

    ratio_clauses = []
    if bal.get("current_ratio") is not None:
        ratio_clauses.append(f"current ratio of {bal['current_ratio']:.2f}x")
    if bal.get("de_ratio") is not None:
        ratio_clauses.append(f"debt-to-equity ratio of {bal['de_ratio']:.2f}x")
    elif bal.get("de_note") and bal["de_note"] not in ("N/A",):
        # e.g. "Not meaningful (negative equity)" — worth stating
        ratio_clauses.append(f"debt-to-equity ratio is {bal['de_note'].lower()}")

    if ratio_clauses:
        # Join two clauses with "and"; one clause stands alone.
        summary_parts.append(f"Its {' and '.join(ratio_clauses)}.")

    if summary_parts:
        summary_text = " ".join(summary_parts)
        print(textwrap.fill(
            summary_text,
            width=70,
            initial_indent="  ",
            subsequent_indent="  ",
        ))
    print()


def print_cash_flow(fin: dict) -> None:
    """
    Print the cash flow section (most recent annual period).

    Displays:
      - Operating Cash Flow
      - Capital Expenditure (shown as a positive spend amount)
      - Free Cash Flow = Operating CF − CapEx

    A note explains the CapEx sign convention used internally so
    the reader is not confused by the positive display of what is
    technically a cash outflow.

    Parameters:
        fin (dict): The dictionary returned by
                    financials.get_financial_statements().
    """
    cf   = fin.get("cashflow", {})
    sym  = fin.get("currency_symbol", "$")
    code = fin.get("currency_code", "USD")
    sep  = "-" * 42

    print()
    print(f"  CASH FLOW  (Most Recent Annual · {code})")
    print(sep)

    if "error" in cf:
        print(f"  {cf['error']}")
        print(sep)
        print()
        return

    def _line(label: str, value: str) -> None:
        print(f"  {label:<26}{value:>12}")

    _line("Operating Cash Flow",  format_financial_value(cf["operating_cf"],   sym))

    # CapEx is stored as a positive spend amount (abs() was applied in
    # financials.py).  We display it prefixed with "−" to make clear it
    # is money going out, without it being a negative number in the data.
    capex_display = format_financial_value(cf["capex"], sym)
    if cf["capex"] is not None:
        capex_display = "−" + capex_display   # Unicode minus for clarity
    _line("Capital Expenditure",  capex_display)

    print(sep)
    _line("Free Cash Flow",       format_financial_value(cf["free_cash_flow"], sym))
    print(sep)

    # ---- Rule-based summary -------------------------------------
    ocf  = cf.get("operating_cf")
    capex = cf.get("capex")
    fcf  = cf.get("free_cash_flow")

    if ocf is not None and capex is not None and fcf is not None:
        summary_text = (
            f"The business generated {format_financial_value(ocf, sym)} in "
            f"operating cash flow and {format_financial_value(fcf, sym)} in "
            f"free cash flow after {format_financial_value(capex, sym)} of "
            f"capital expenditure."
        )
    elif ocf is not None:
        summary_text = (
            f"The business generated {format_financial_value(ocf, sym)} in "
            f"operating cash flow."
        )
        if fcf is not None:
            summary_text += f" Free cash flow was {format_financial_value(fcf, sym)}."
    else:
        summary_text = ""

    if summary_text:
        print(textwrap.fill(
            summary_text,
            width=70,
            initial_indent="  ",
            subsequent_indent="  ",
        ))
    print()


def print_ratios(ratios: dict, fin: dict) -> None:
    """
    Print the Financial Ratios & Valuation section.

    Organised into three subsections matching the three dicts returned
    by financials.get_ratios():
      1. Profitability  — EPS, margins, ROE, ROA
      2. Financial Strength — D/E, current ratio, cash-to-debt
      3. Market Valuation  — P/E, PEG, EV, EBITDA, EV/EBITDA, P/B

    Each ratio is shown as:
        Ratio Name                         Value
          One-sentence description.

    Parameters:
        ratios (dict): Returned by financials.get_ratios().
        fin    (dict): Returned by financials.get_financial_statements();
                       used only for the currency symbol.
    """
    sym  = fin.get("currency_symbol", "$")
    sep  = "=" * 58   # main section header
    dash = "-" * 58   # subsection separator

    print()
    print(f"  {sep}")
    print(f"  FINANCIAL RATIOS & VALUATION")
    print(f"  {sep}")

    def _ratio_line(label: str, value: str, description: str) -> None:
        """
        Print one ratio entry: label + right-aligned value, then a
        description on the next line indented by four spaces.

        The label is left-aligned in 34 characters; the value is
        right-aligned in 14 characters, giving a total line width
        of 2 (indent) + 34 + 14 = 50 characters.
        """
        print(f"  {label:<34}{value:>14}")
        print(textwrap.fill(
            description,
            width=64,
            initial_indent="    ",
            subsequent_indent="    ",
        ))
        print()

    # ================================================================
    # Section 1 — Profitability
    # ================================================================
    prof = ratios.get("profitability", {})

    print()
    print(f"  Profitability")
    print(f"  {dash}")
    print()

    _ratio_line(
        "EPS (Diluted)",
        format_eps(prof.get("eps"), sym),
        "Profit earned for each outstanding share.",
    )
    _ratio_line(
        "Net Margin",
        format_percent(prof.get("net_margin")),
        "Percentage of revenue that becomes profit after all expenses.",
    )
    _ratio_line(
        "Operating Margin",
        format_percent(prof.get("op_margin")),
        "Percentage of revenue remaining after operating expenses.",
    )
    _ratio_line(
        "Return on Equity (ROE)",
        format_percent(prof.get("roe")),
        "Measures how efficiently shareholder capital generates profit.",
    )
    _ratio_line(
        "Return on Assets (ROA)",
        format_percent(prof.get("roa")),
        "Measures how efficiently company assets generate profit.",
    )

    # ================================================================
    # Section 2 — Financial Strength
    # ================================================================
    strength = ratios.get("strength", {})

    print(f"  Financial Strength")
    print(f"  {dash}")
    print()

    # D/E ratio: may be a numeric float or a plain-text note (e.g.
    # "Not meaningful (negative equity)") — mirror the balance sheet logic.
    de_ratio = strength.get("de_ratio")
    de_note  = strength.get("de_note")
    de_value = f"{de_ratio:.2f}x" if de_ratio is not None else (de_note or "N/A")

    _ratio_line(
        "Debt-to-Equity",
        de_value,
        "Shows how much debt is used relative to shareholder capital.",
    )

    cr = strength.get("current_ratio")
    _ratio_line(
        "Current Ratio",
        f"{cr:.2f}x" if cr is not None else "N/A",
        "Measures the ability to pay short-term obligations.",
    )

    ctd = strength.get("cash_to_debt")
    _ratio_line(
        "Cash-to-Debt Ratio",
        f"{ctd:.2f}x" if ctd is not None else "N/A",
        "Compares available cash with total debt.",
    )

    # ================================================================
    # Section 3 — Market Valuation
    # ================================================================
    # These values come directly from Yahoo Finance (ticker.info) and
    # reflect live market prices and analyst estimates.
    val = ratios.get("valuation", {})

    print(f"  Market Valuation")
    print(f"  {dash}")
    print()

    trailing_pe = val.get("trailing_pe")
    forward_pe  = val.get("forward_pe")
    peg         = val.get("peg")
    ev          = val.get("ev")
    ebitda      = val.get("ebitda")
    ev_ebitda   = val.get("ev_ebitda")
    pb          = val.get("pb")

    _ratio_line(
        "Trailing P/E",
        f"{trailing_pe:.1f}x" if trailing_pe is not None else "N/A",
        "How much investors pay for each dollar of earnings.",
    )
    _ratio_line(
        "Forward P/E",
        f"{forward_pe:.1f}x" if forward_pe is not None else "N/A",
        "Values the company using expected future earnings.",
    )
    _ratio_line(
        "PEG Ratio",
        f"{peg:.2f}x" if peg is not None else "N/A",
        "Adjusts the P/E ratio for expected earnings growth.",
    )
    _ratio_line(
        "Enterprise Value",
        format_financial_value(ev, sym),
        "The total value of the business including debt and cash.",
    )
    _ratio_line(
        "EBITDA",
        format_financial_value(ebitda, sym),
        "Operating earnings before interest, tax, depreciation and amortisation.",
    )
    _ratio_line(
        "EV / EBITDA",
        f"{ev_ebitda:.1f}x" if ev_ebitda is not None else "N/A",
        "Compares enterprise value with operating earnings.",
    )
    _ratio_line(
        "Price-to-Book (P/B)",
        f"{pb:.2f}x" if pb is not None else "N/A",
        "Compares market value with accounting book value.",
    )

    print(f"  {dash}")
    print()


def format_price(value: float | None) -> str:
    """Format a share price, or show ``N/A`` when it is unavailable."""
    return f"${value:,.2f}" if value is not None else "N/A"


def format_return(value: float | None) -> str:
    """Format a decimal return as a signed percentage."""
    if value is None:
        return "N/A"
    return f"{value:+.1%}"


def format_distance(value: float | None) -> str:
    """Format a non-directional percentage distance from a price range."""
    return f"{value:.1%}" if value is not None else "N/A"


def format_percentage_points(value: float | None) -> str:
    """Format a return difference as signed percentage points."""
    if value is None:
        return "N/A"
    return f"{value * 100:+.1f} pp"


def print_performance(performance: dict) -> None:
    """Print historical returns, the 52-week range, and S&P 500 comparison."""
    separator = "-" * 58
    returns = performance.get("returns", {})
    price_range = performance.get("range", {})
    benchmark = performance.get("benchmark", {})

    print()
    print(f"  {separator}")
    print("  STOCK PRICE PERFORMANCE")
    print(f"  {separator}")
    for label in ("1 Month", "6 Months", "1 Year", "3 Years", "5 Years"):
        print(f"  {label:<24}{format_return(returns.get(label)):>14}")

    print()
    print("  52-WEEK RANGE")
    print(f"  {separator}")
    print(f"  {'Current Price':<24}{format_price(price_range.get('current_price')):>14}")
    print(f"  {'52-Week High':<24}{format_price(price_range.get('high')):>14}")
    print(f"  {'52-Week Low':<24}{format_price(price_range.get('low')):>14}")
    print(f"  {'Below 52-Week High':<24}{format_distance(price_range.get('below_high')):>14}")
    print(f"  {'Above 52-Week Low':<24}{format_distance(price_range.get('above_low')):>14}")

    print()
    print("  VS S&P 500")
    print(f"  {separator}")
    print(f"  {'':<16}{'Stock':>14}{'S&P 500':>14}{'Difference':>14}")
    for label in ("1 Year", "3 Years", "5 Years"):
        values = benchmark.get(label, {})
        print(
            f"  {label:<16}{format_return(values.get('stock')):>14}"
            f"{format_return(values.get('benchmark')):>14}"
            f"{format_percentage_points(values.get('difference')):>14}"
        )

    summary = _performance_summary(performance)
    if summary:
        print()
        print(textwrap.fill(summary, width=70, initial_indent="  ", subsequent_indent="  "))
    print()


def _performance_summary(performance: dict) -> str:
    """Create a short factual summary from available performance values."""
    returns = performance.get("returns", {})
    comparison = performance.get("benchmark", {}).get("1 Year", {})
    one_year = returns.get("1 Year")
    difference = comparison.get("difference")

    if one_year is not None and difference is not None:
        direction = "outperformed" if difference >= 0 else "underperformed"
        return (
            f"The stock returned {format_return(one_year)} over the past year and "
            f"{direction} the S&P 500 by {abs(difference) * 100:.1f} percentage points."
        )
    if one_year is not None:
        return f"The stock returned {format_return(one_year)} over the past year."

    missing_long_term = all(returns.get(label) is None for label in ("3 Years", "5 Years"))
    if missing_long_term:
        return "The stock does not have enough trading history for some long-term performance periods."
    return "Some stock or benchmark performance comparisons are unavailable."


def print_error(message: str) -> None:
    """
    Print a clearly labelled error message to the terminal.

    Parameters:
        message (str): The error description to display.
    """
    print(f"\n  [ERROR] {message}\n")


def print_welcome() -> None:
    """
    Print a welcome banner when the application starts.
    """
    print()
    print("=" * 40)
    print("  Investment Research Assistant")
    print("=" * 40)
    print("  Type a stock ticker to look it up.")
    print("  Type 'quit' or 'q' to exit.")
    print("=" * 40)
    print()
