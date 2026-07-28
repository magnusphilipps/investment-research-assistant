# ============================================================
# main.py — Application Logic
# ============================================================
#
# PURPOSE:
#   This is the "brain" of the application. It doesn't fetch
#   data itself, and it doesn't format output itself — it
#   delegates those jobs to the other modules and coordinates
#   the overall flow.
#
# FLOW:
#   1. Show a welcome message.
#   2. Ask the user to type a ticker symbol.
#   3. Pass the ticker to fetcher.get_stock_info().
#   4. If data comes back, pass it to display.print_stock_info().
#   5. If something goes wrong, show a helpful error.
#   6. Repeat until the user types 'quit'.
# ============================================================

# We import our own modules from the same package.
# The dot (.) means "from the current package (investment_research)".
from . import fetcher
from . import financials
from . import display


def run() -> None:
    """
    Main loop of the Investment Research Assistant.

    This function runs until the user chooses to exit.
    A "loop" in Python repeats a block of code indefinitely
    until you explicitly break out of it with `break`.
    """

    # Show the welcome banner once, when the program starts.
    display.print_welcome()

    # `while True` creates an infinite loop.
    # The only way out is a `break` statement inside the loop.
    while True:

        # input() pauses the program and waits for the user to type
        # something and press Enter. It returns whatever they typed
        # as a string.
        raw_input = input("  Enter ticker symbol: ")

        # .strip() removes any accidental spaces before/after the text.
        # .upper() converts to uppercase so "aapl" works like "AAPL".
        ticker = raw_input.strip().upper()

        # If the user typed nothing, skip this iteration of the loop
        # and ask again. `continue` jumps back to the top of the loop.
        if not ticker:
            display.print_error("Please enter a ticker symbol.")
            continue

        # Let the user exit cleanly by typing 'quit' or 'q'.
        if ticker in ("QUIT", "Q"):
            print("\n  Goodbye!\n")
            break  # Exit the while loop, ending the program.

        # Tell the user we are working — network requests can take a moment.
        print(f"\n  Looking up {ticker}...")

        # Attempt to fetch the stock data.
        # We wrap this in a try/except block to handle unexpected errors
        # gracefully (e.g. no internet connection, API timeout).
        try:
            data = fetcher.get_stock_info(ticker)
        except Exception as error:
            # `Exception` catches most runtime errors.
            # We log the raw error message so the user can see what went wrong.
            display.print_error(f"Could not retrieve data: {error}")
            continue  # Go back to the top of the loop and ask again.

        # If fetcher returned None, the ticker was invalid or had no data.
        if data is None:
            display.print_error(
                f"'{ticker}' does not appear to be a valid ticker symbol. "
                "Double-check it and try again."
            )
            continue

        # All good — display Phase 1 and Phase 2 information.
        # Each function receives the same `data` dictionary; they each
        # just read the keys that belong to their section.
        display.print_stock_info(data)
        display.print_company_overview(data)

        # Phase 3 — Financial Statements.
        # financials.get_financial_statements() makes a separate set of
        # yfinance calls (.financials, .balance_sheet, .cashflow) which
        # return pandas DataFrames.  We wrap this in its own try/except
        # so a failure here does not hide the Phase 1/2 output already
        # printed above.
        try:
            fin = financials.get_financial_statements(ticker)
        except Exception as error:
            display.print_error(f"Could not retrieve financial statements: {error}")
            continue

        if fin is None:
            # This should not happen (ticker already validated above),
            # but we handle it defensively.
            display.print_error("Financial statement data unavailable for this ticker.")
            continue

        display.print_income_statement(fin)
        display.print_balance_sheet(fin)
        display.print_cash_flow(fin)
