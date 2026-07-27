# Investment Research Assistant

A Python console application for looking up basic stock information.
Enter a ticker symbol and it retrieves the company name, current share
price, and market capitalisation from Yahoo Finance.

This is a long-term learning project. Each version adds one layer of
capability while keeping the code simple, modular, and well commented.

---

## Current Features (v1)

- Interactive terminal prompt — type a ticker, get results instantly
- Looks up: company name, current share price, market capitalisation
- Market cap displayed in human-readable form (Millions / Billions / Trillions)
- Graceful error handling for invalid tickers and network problems
- Loop continues until you type `quit`

---

## How to Run

Open a terminal and run:

```bash
python run.py
```

Then type any stock ticker at the prompt:

```
  Enter ticker symbol: AAPL

  Looking up AAPL...

----------------------------------------
  Apple Inc. (AAPL)
----------------------------------------
  Share Price  :  $195.50
  Market Cap   :  $3.01 Trillion
----------------------------------------
```

Type `quit` or `q` to exit.

---

## Project Structure

```
investment_research_assistant/
│
├── run.py                          # Entry point — run this to start the app
│
├── investment_research/            # All application code lives here
│   ├── __init__.py                 # Marks the folder as a Python package
│   ├── main.py                     # Application loop and user interaction
│   ├── fetcher.py                  # Fetches stock data via yfinance
│   └── display.py                  # Formats and prints output to the terminal
│
├── README.md                       # This file
├── replit.md                       # Developer notes and project overview
├── requirements.txt                # Python dependencies
└── .gitignore                      # Files excluded from version control
```

### File Purposes

| File | Responsibility |
|---|---|
| `run.py` | Single entry point. Imports `main.run()` and calls it. |
| `investment_research/main.py` | The application loop. Reads user input, calls fetcher and display, handles errors. |
| `investment_research/fetcher.py` | All data-fetching logic. Uses `yfinance` to retrieve stock info. Returns a plain dictionary. |
| `investment_research/display.py` | All output-formatting logic. Converts raw numbers into readable strings and prints them. |
| `investment_research/__init__.py` | Empty marker file. Required by Python to treat the folder as an importable package. |

---

## Development Roadmap

The project grows in deliberate, small steps. Each phase introduces
one new concept without requiring changes to existing code.

### Phase 1 — Basic Lookup ✅
- Console app with a live prompt
- Company name, share price, market cap via yfinance

### Phase 2 — Richer Data (planned)
- 52-week high / low
- P/E ratio and dividend yield
- Sector and industry

### Phase 3 — Watchlist (planned)
- Save a list of tickers to a local file
- Look up all tickers in the watchlist in one command

### Phase 4 — Historical Prices (planned)
- Fetch price history for a given period
- Display a simple ASCII chart in the terminal

### Phase 5 — Export (planned)
- Save results to a CSV file for use in spreadsheets

### Phase 6 — Web Interface (planned)
- Simple web UI using Flask or FastAPI
- Display the same data in a browser

---

## Dependencies

| Package | Purpose |
|---|---|
| `yfinance` | Fetches stock data from Yahoo Finance |

Install all dependencies with:

```bash
pip install -r requirements.txt
```

---

## Python Version

Python 3.10 or later (uses `X | Y` union type hints).
