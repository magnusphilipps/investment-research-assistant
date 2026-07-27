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
# ============================================================


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
