# Investment Research Assistant

A Python console application that looks up basic stock information — company name, share price, and market capitalisation — using the yfinance library.

## How to Run

Open the Shell tab and type:

```
python run.py
```

Then type any stock ticker (e.g. `AAPL`, `MSFT`, `TSLA`) and press Enter.
Type `quit` or `q` to exit.

## Project Structure

```
run.py                          ← Entry point. Run this file to start the app.
investment_research/
  __init__.py                   ← Marks the folder as a Python package (can be empty).
  main.py                       ← Application loop — coordinates fetching and display.
  fetcher.py                    ← Fetches stock data from Yahoo Finance via yfinance.
  display.py                    ← Formats and prints results to the terminal.
```

## Dependencies

- `yfinance` — fetches stock data from Yahoo Finance

## Stack

- Python 3 (standard library + yfinance)
- No web server, no database, no JavaScript

## User Preferences

- Keep everything simple, modular, and well commented — this is a learning project.
- Python only for now. No JavaScript, no web UI.
- No AI features in the first version.
- Every file should be explained for a learner.
