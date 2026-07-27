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
#     - fetcher.py  →  knows HOW to get data
#     - display.py  →  knows HOW to show data
#     - main.py     →  coordinates the two
#
#   This makes each file easier to read, test, and change.
#
# NEW IN PHASE 2:
#   - format_employees()      — formats a headcount integer readably
#   - print_company_overview() — prints the six new overview fields
#   - textwrap is imported to word-wrap long business descriptions
# ============================================================

# textwrap is part of Python's standard library — no installation needed.
# It provides utilities for wrapping and filling text to a fixed width,
# which is useful when printing long paragraphs in a terminal.
import textwrap


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
