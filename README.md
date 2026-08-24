# Investment Research Assistant

A Python console application for researching publicly traded companies.
Enter a ticker symbol, and it retrieves a price snapshot, company overview,
and full financial statements from Yahoo Finance.

This is a long-term learning project. Each version adds one layer of
capability while keeping the code simple, modular, and well commented.

---

## Current Features (v6)

- **Analyst Expectations & Forward Outlook (Feature 6)**: Displays analyst price targets, recommendation counts, and (where available) forward revenue estimates. Shows current price, average/median/high/low analyst targets, number of analysts, and the implied upside/downside using (Target / Current) - 1. Recommendation counts are presented by category (Strong Buy / Buy / Hold / Sell / Strong Sell). Missing data is shown as `N/A`. This feature is purely factual: it surfaces analyst estimates and does not provide investment recommendations.

- Interactive terminal prompt — type a ticker, get results instantly
- **Price snapshot:** company name, current share price, market capitalisation
- **Company overview:** sector, industry, country, employee count, website, business description
- **Income statement:** revenue, gross profit, operating income, net income, EPS, diluted shares — up to four annual periods side by side
- **Revenue growth** calculated year-on-year with a trend label (Accelerating / Slowing / Broadly stable / Unavailable)
- **Year-on-year margin changes** shown in percentage points beside the latest gross and operating margins
- **Balance sheet:** cash, total debt, shareholders equity, D/E ratio, current assets/liabilities, current ratio, retained earnings
- **Cash flow:** operating cash flow, capital expenditure, free cash flow
- **Rule-based factual summaries** after each financial section — derived only from the displayed data, no qualitative claims
- **Financial Ratios & Valuation** — three subsections:
  - *Profitability:* EPS, net margin, operating margin, ROE, ROA
  - *Financial Strength:* debt-to-equity, current ratio, cash-to-debt ratio
  - *Market Valuation:* trailing P/E, forward P/E, PEG, enterprise value, EBITDA, EV/EBITDA, price-to-book
- **Stock Price Performance:** adjusted historical returns for 1 month, 6 months, 1 year, 3 years, and 5 years
- **52-week range:** current adjusted price, high, low, and distance from each boundary
- **S&P 500 comparison:** 1-year, 3-year, and 5-year stock returns versus `^GSPC` in percentage points
- Values displayed in the company's reporting currency (USD, GBP, EUR, etc.)
- Large figures formatted compactly: `$391.0B`, `£8.7M`, `-$3.7B`
- Missing fields shown as `N/A` rather than crashing
- Banks and unusual statement structures handled gracefully
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
│   ├── fetcher.py                  # Fetches price snapshot + overview via yfinance
│   ├── financials.py               # Fetches, extracts, and calculates financial statements
│   ├── performance.py               # Fetches adjusted prices and calculates performance metrics
│   └── display.py                  # Formats and prints all output to the terminal
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
| `investment_research/main.py` | The application loop. Reads user input, calls all modules, handles errors. |
| `investment_research/fetcher.py` | Fetches price, market cap, and company overview from `ticker.info`. |
| `investment_research/financials.py` | Fetches annual statements (DataFrames), extracts line items with fallback label lists, calculates margins/ratios/FCF. |
| `investment_research/performance.py` | Fetches adjusted historical prices, calculates returns and the 52-week range, and compares the stock with the S&P 500. |
| `investment_research/display.py` | All formatting and printing. Never calculates; only presents. |
| `investment_research/__init__.py` | Empty marker file. Required by Python to treat the folder as an importable package. |

---

## Financial Statement Formulas

### Gross Margin
```
Gross Margin = Gross Profit / Revenue × 100
```
Measures how much revenue remains after direct production costs.
A higher margin means the company retains more from each sale before
paying operating expenses.

### Operating Margin
```
Operating Margin = Operating Income / Revenue × 100
```
Measures profitability after both production costs and operating expenses
(salaries, R&D, SG&A). Shows how efficiently the business is run.

### Revenue Growth
```
Revenue Growth = (Revenue_current − Revenue_prior) / Revenue_prior × 100
```
The percentage change in revenue from one annual period to the next.
Calculated for each year shown. The oldest year always shows N/A because
there is no prior year to compare it against.

### Revenue Growth Trend
```
Trend = Latest annual growth rate − Prior annual growth rate
```
- **Accelerating:** difference > +1 percentage point
- **Slowing:** difference < −1 percentage point
- **Broadly stable:** within ±1 percentage point
- **Unavailable:** fewer than three years of revenue data

### Year-on-Year Margin Change
```
YoY Change (pp) = Latest year margin − Prior year margin
```
Expressed in **percentage points (pp)**, not percentage growth.
For example, a gross margin rising from 44.1% to 46.2% is reported
as `+2.1 pp` — not as `+4.8%`, which would be the percentage change
of the margin itself. Only the most recent year is compared; older
years show no YoY change because the table already displays the
values side by side.

### Rule-Based Summaries
After each financial section, a one- or two-sentence summary states
the key facts in plain English. The summaries are generated entirely
from the computed data using `if/elif` logic — no language model or
qualitative judgement is involved. They do not make any claim about
financial safety, risk, or investment merit.

---

## Feature 4 — Financial Ratios & Valuation

### Manually Calculated Ratios

The following ratios are computed directly from the financial
statement data already retrieved in Feature 3. No additional network
call is made for these.

#### Net Margin
```
Net Margin = Net Income / Revenue × 100
```
The percentage of revenue that remains as profit after all expenses
including tax. A higher net margin means more of each revenue dollar
reaches the bottom line.

#### Return on Equity (ROE)
```
ROE = Net Income / Shareholders Equity × 100
```
Measures how much profit the company generates for every dollar of
shareholder capital. Shown as N/A when equity is zero or negative,
because the ratio becomes misleading in those cases (the same
reasoning as Debt-to-Equity).

#### Return on Assets (ROA)
```
ROA = Net Income / Total Assets × 100
```
Measures how efficiently the company's entire asset base generates
profit. A higher ROA indicates the business needs fewer assets to
produce the same earnings.

#### Cash-to-Debt Ratio
```
Cash-to-Debt = Cash & Equivalents / Total Debt
```
Compares the company's liquid cash with its total debt load. A ratio
of 1.0x would mean cash exactly covers the debt; below 1.0x means
it does not.

#### EV / EBITDA
```
EV / EBITDA = Enterprise Value / EBITDA
```
Calculated manually from the Enterprise Value and EBITDA figures
retrieved from Yahoo Finance. Shown as N/A if either input is
unavailable or zero.

### Ratios Retrieved Directly from Yahoo Finance

The following metrics are **not** recalculated from statements.
They are read directly from `ticker.info` as returned by `yfinance`:

| Metric | Yahoo Finance key | Why not recreated |
|---|---|---|
| Trailing P/E | `trailingPE` | Requires the live share price, which changes continuously |
| Forward P/E | `forwardPE` | Uses analyst consensus EPS forecasts not available in statements |
| PEG Ratio | `pegRatio` | Requires an earnings growth rate estimated by analysts |
| Enterprise Value | `enterpriseValue` | Incorporates market capitalisation, which is live |
| EBITDA | `ebitda` | Yahoo Finance computes this from multiple statement lines; replicating it exactly is error-prone |
| Price-to-Book | `priceToBook` | Requires the live share price divided by book value per share |

**Why retrieve rather than recreate?**
Valuation metrics that include the share price or analyst estimates
are inherently live figures. Recreating them from annual statement
snapshots would give values that are hours or days stale and would
not match what any financial data provider shows. Using the
pre-computed values from Yahoo Finance gives results that are
consistent with the source.

### Feature 4 Limitations

- **EV/EBITDA for banks and financial companies:** Yahoo Finance
  often does not report EBITDA for banks (e.g. JPM), so EV/EBITDA
  shows N/A. This is correct — EBITDA is not a standard metric for
  financial institutions.
- **NBIS (and other early-stage companies):** Negative EBITDA
  produces a mathematically valid but practically uninterpretable
  EV/EBITDA multiple. The application displays the computed figure
  rather than suppressing it, so the user can see the sign.
- **Forward P/E:** May be negative if the consensus forecast
  projects a net loss. The value is shown as-is.
- **ROE for negative-equity companies:** Shown as N/A to avoid
  a misleading positive ratio caused by two negatives dividing.

## Feature 5 — Stock Price Performance

Feature 5 adds a factual view of historical share-price performance. It
uses adjusted historical prices from yfinance, so splits and other relevant
adjustments do not distort the comparison.

### Historical Returns

The application displays returns for 1 month, 6 months, 1 year, 3 years,
and 5 years. For each period it finds the latest available trading price on
or before the target start date rather than assuming that every calendar date
has a market price.

```
Return = (Ending Price / Starting Price) - 1
```

The ending price is the latest available adjusted close. If the company did
not trade for the full period, the result is `N/A`; the application does not
extrapolate a shorter history.

### 52-Week Range

The range uses the latest 52 calendar weeks of raw daily `High` and `Low`
prices. It displays the latest closing price, the highest and lowest prices
in that window, how far the current price is below the high, and how far it is
above the low. This reflects the actual intraday trading range rather than
only closing prices.

### S&P 500 Comparison

The stock's 1-year, 3-year, and 5-year returns are compared with the S&P 500
Yahoo Finance ticker `^GSPC`. The difference is shown in percentage points:

```
Difference (pp) = Stock Return - S&P 500 Return
```

Each side uses the same period. If the stock or benchmark lacks sufficient
history, that comparison is shown as `N/A`. A failed benchmark request does
not hide the stock's own performance data.

Newly listed companies may not have enough trading history for every period,
so their longer-term returns and comparisons can be unavailable.

Yahoo Finance also exposes `firstTradeDate` through yfinance history metadata.
The application uses that as a conservative lower boundary when available.
However, it describes the first trade Yahoo associates with a ticker's
continuous price series, not necessarily the date the current company began
trading. It cannot reliably distinguish predecessor or SPAC history after a
business combination, so no company-specific cutoff is applied. In such
cases, Yahoo's historical data may still make a long-term return appear
available when the current company has not traded for that long.

---

### Debt-to-Equity Ratio
```
D/E Ratio = Total Debt / Shareholders Equity
```
Indicates how much of the business is funded by debt versus equity.
A ratio above 1.0 means more debt than equity. Shown as "Not meaningful"
when equity is zero or negative, because the ratio becomes misleading
in those cases.

### Current Ratio
```
Current Ratio = Current Assets / Current Liabilities
```
Measures short-term liquidity. A ratio below 1.0 suggests the company
may struggle to cover near-term obligations with liquid assets alone.
Banks and financial companies typically do not report current assets or
liabilities; this field shows N/A for them.

### Free Cash Flow
```
Free Cash Flow = Operating Cash Flow − Capital Expenditure
```
The cash a business generates after maintaining and growing its physical
asset base. Positive FCF means the business is self-funding; negative FCF
may indicate heavy investment or operational challenges.

Capital expenditure is normalised to a positive spend amount internally
(some data sources report it as a negative outflow). The display prefixes
it with `−` to make the direction clear.

---

## Data Availability Notes

- **Annual periods only.** All financial statement data uses annual figures,
  not quarterly. Up to four annual periods are shown.
- **Label variation.** Yahoo Finance uses different accounting labels for
  different companies and industries. Each line item is looked up using a
  ranked list of alternative names; if none match, `N/A` is shown.
- **Banks and financial companies** (e.g. JPM) do not report gross profit,
  current assets, or current liabilities in the standard way. These fields
  show `N/A`, which is correct behaviour.
- **Early-stage companies** may have negative margins and missing fields —
  the application displays these correctly rather than hiding them.
- **Reporting currency** varies by company. Values are shown in the currency
  the company uses for its financial statements (e.g. £ for UK companies).

---

## Development Roadmap

The project grows in deliberate, small steps. Each phase introduces
one new concept without requiring changes to existing code.

### Phase 1 — Basic Lookup ✅
- Console app with a live prompt
- Company name, share price, market cap via yfinance

### Phase 2 — Company Overview ✅
- Sector, industry, country, employee count, website
- Full business description, word-wrapped for readability

### Phase 3 — Financial Statements ✅
- Annual income statement: revenue, margins, EPS, diluted shares
- Revenue growth and trend label (Accelerating / Slowing / Broadly stable)
- Year-on-year margin changes in percentage points beside the latest figures
- Balance sheet: cash, debt, equity, ratios
- Cash flow: operating CF, CapEx, free cash flow
- Rule-based factual summary after each section
- Multi-currency support; graceful N/A handling

### Phase 4 — Financial Ratios & Valuation ✅
- **Profitability:** EPS (diluted), net margin, operating margin, ROE, ROA
- **Financial Strength:** debt-to-equity, current ratio, cash-to-debt ratio
- **Market Valuation:** trailing P/E, forward P/E, PEG ratio, enterprise value, EBITDA, EV/EBITDA, price-to-book
- Each ratio displayed with a one-sentence plain-English description
- Calculated ratios derived from statements; market ratios sourced from Yahoo Finance

### Phase 5 — Stock Price Performance ✅
- Adjusted historical returns for 1 month, 6 months, 1 year, 3 years, and 5 years
- 52-week high / low and current price position
- S&P 500 benchmark comparison for 1 year, 3 years, and 5 years

### Phase 6 — Watchlist (planned)
- Save a list of tickers to a local file
- Look up all tickers in the watchlist in one command

### Phase 7 — Historical Prices (planned)
- Fetch price history for a given period
- Display a simple ASCII chart in the terminal

### Phase 8 — Export (planned)
- Save results to a CSV file for use in spreadsheets

### Phase 9 — Web Interface (planned)
- Simple web UI using Flask or FastAPI
- Display the same data in a browser

---

## Dependencies

| Package | Purpose |
|---|---|
| `yfinance` | Fetches stock data and financial statements from Yahoo Finance |
| `pandas` | Installed automatically with yfinance; used to work with DataFrame results |

Install all dependencies with:

```bash
pip install -r requirements.txt
```

---

## Python Version

Python 3.10 or later (uses `X | Y` union type hints).
