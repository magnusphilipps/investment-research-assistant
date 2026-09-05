# Investment Research Assistant

A Python console application for researching publicly traded companies.
Enter a ticker symbol, and it retrieves a price snapshot, company overview,
and full financial statements from Yahoo Finance.

This is a long-term learning project. Each version adds one layer of
capability while keeping the code simple, modular, and well commented.

---

## Current Features (v9)

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
- **Recent News & Developments (Feature 8):** up to three recent English-language, company-specific Marketaux articles with source, date, concise description, and original URL
- **Grounded AI Analysis (Feature 9):** structured Gemini synthesis of the evidence already collected by Features 1–8, with no new financial-data requests, recommendations, or target prices
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
│   ├── news.py                     # Fetches and standardises Marketaux news
│   ├── analysis.py                 # Builds compact Feature 9 evidence context
│   ├── gemini_provider.py          # Isolated Google Gemini provider integration
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
| `investment_research/news.py` | Reads `MARKETAUX_API_KEY`, requests recent Marketaux news, standardises article metadata, and handles API failures. |
| `investment_research/analysis.py` | Converts Feature 1–8 result dictionaries into a compact, JSON-safe AI evidence context. |
| `investment_research/gemini_provider.py` | Calls Gemini with grounded instructions, validates structured JSON, and hides provider failures. |
| `investment_research/performance.py` | Fetches adjusted historical prices, calculates returns and the 52-week range, and compares the stock with the S&P 500. |
| `investment_research/display.py` | All formatting and printing, including Feature 8 article links and URL fallbacks. |
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

### Phase 8 — Recent News & Developments ✅
- Recent company-specific English-language news from Marketaux
- Up to three recent articles per ticker, filtered by ticker/entity association
- Source, UTC-formatted publication date, concise description, and original URL
- Clickable headlines in terminals supporting OSC-8 links, with URL fallback
- Graceful handling for missing keys, API errors, empty responses, malformed data, and duplicates

### Phase 9 — Grounded AI Analysis ✅
- Builds a compact evidence package from the structured results already collected by Features 1–8
- Uses Google Gemini model `gemini-3.6-flash` through the official `google-genai` SDK
- Returns structured JSON sections for financial performance, financial position, valuation, share price and expectations, peer positioning, recent developments, and key factors to watch
- Uses `GOOGLE_API_KEY` from Replit Secrets; the key is never printed, stored in source, or included in errors
- Explicitly grounds factual claims in supplied evidence and represents missing information as unavailable rather than zero
- Keeps provider-specific Gemini code isolated in `gemini_provider.py`
- Does not make Buy/Hold/Sell recommendations, personalized financial advice, sentiment scores, or unsupported price targets
- Gemini/API failures are isolated and display `AI analysis temporarily unavailable.` while Features 1–8 continue normally

### Phase 10 — Export (planned)
- Save results to a CSV file for use in spreadsheets

### Phase 11 — Web Interface (planned)
- Simple web UI using Flask or FastAPI
- Display the same data in a browser

---

## Dependencies

| Package | Purpose |
|---|---|
| `yfinance` | Fetches stock data and financial statements from Yahoo Finance |
| `pandas` | Installed automatically with yfinance; used to work with DataFrame results |
| `requests` | Sends the single Marketaux REST API request for recent news |

Install all dependencies with:

```bash
pip install -r requirements.txt
```

---

## Python Version

Python 3.10 or later (uses `X | Y` union type hints).

# Learning Guide

This Learning Guide summarizes each feature, the main files involved, and the key Python/pandas concepts used while building them. It is aimed at a developer learning Python.

## Feature 1 — Foundation
- What it does: Basic ticker lookup and price snapshot.
- Main files: `fetcher.py`, `run.py`, `main.py`.
- Key concepts: calling library functions (`yfinance`), dictionaries, simple I/O (`input()` / `print()`).
- Suggestion: study how `fetcher.get_stock_info()` gathers `ticker.info`.

## Feature 2 — Company Overview
- What it does: Shows sector, industry, country, employees, website and a shortened business description.
- Main files: `fetcher.py`, `display.py`.
- Key concepts: string handling, text wrapping (`textwrap.fill()`), deterministic sentence splitting for a short description (`shorten_description()` in `display.py`).
- Note: The long yfinance description is kept in the backend but displayed in a shortened 3–4 sentence paragraph for readability.

## Feature 3 — Financial Statements
- What it does: Fetches annual income, balance sheet and cash flow statements and extracts key line items.
- Main files: `financials.py`, `display.py`.
- Key concepts: pandas DataFrames returned by `yfinance`, robust row label lookup via ranked candidate labels, safe arithmetic (`_safe_divide()`), percentage calculations (`_pct()`).
- Suggestion: study `_extract_value()` for defensive data extraction from DataFrames.

## Feature 4 — Financial Ratios & Valuation
- What it does: Computes profitability, strength and valuation metrics by reusing the statements already retrieved.
- Main files: `financials.py`, `display.py`.
- Key concepts: reusing computed data rather than refetching, live market metrics from `ticker.info`, and distinction between derived ratios and market-derived valuations.
- Suggestion: study `get_ratios()` to see how statement-derived ratios and `yfinance`-derived valuation metrics are combined.

## Feature 5 — Stock Price Performance
- What it does: Computes adjusted historical returns, 52-week range, and S&P 500 comparisons.
- Main files: `performance.py`, `display.py`.
- Key concepts: working with time-series price data, handling missing history gracefully, percentage-return calculations.

## Feature 6 — Analyst Expectations & Forward Outlook
- What it does: Shows analyst price targets, recommendation counts and revenue estimates where available.
- Main files: `expectations.py`, `display.py`.
- Key concepts: structured dictionaries for presenting grouped data; formatting helpers like `format_price()` and `format_pct_fraction()`.

## Feature 7 — Peer Comparison (added)
- What it does: Compares the selected company with three manually configured peers on a compact set of metrics and prints a very short factual summary.
- Main files: `investment_research/peers.py`, `investment_research/display.py`, `investment_research/main.py`.
- Metrics compared: Revenue Growth (most recent YoY), Operating Margin, ROE, Debt-to-Equity, P/E (trailing), Forward P/E, EV/EBITDA.
- Peer selection: Manually configured in `PEERS` inside `investment_research/peers.py`. This keeps selection simple and editable.
- Implementation notes:
  - `peers.fetch_peer_comparison(ticker)` builds a pandas DataFrame of raw numeric values (or None) for the target + three peers and returns a short rule-based summary.
  - The display layer formats values (percent, x.xx multiples) and prints a compact table using existing `display.py` helpers.
  - Missing values are represented as `N/A` in the output; missing peers show a clear message rather than crashing.
- Why it’s educational: demonstrates how to reuse existing functions (`get_financial_statements` and `get_ratios`), how to handle incomplete data defensively, and how to separate data from presentation.

## Feature 8 — Recent News & Developments

### What it does
Feature 8 retrieves up to three recent, company-specific financial-news
articles from Marketaux when a ticker is searched. It shows each article's
headline, publisher, publication date, short API-provided description, and
original URL. It does not interpret the news or make an investment judgement.

### Main files and data flow
```text
Ticker
  ↓
Marketaux REST request
  ↓
JSON response
  ↓
news.py cleans and standardises article metadata
  ↓
main.py orchestrates
  ↓
display.py formats the section and headline links
  ↓
terminal
```

- `investment_research/news.py` reads `MARKETAUX_API_KEY`, sends one
  economical request to Marketaux, validates the response, removes duplicates,
  shortens descriptions, and returns simple article dictionaries.
- `main.py` calls `news.get_company_news(ticker)` after the existing features
  and keeps news failures isolated from the rest of the report.
- `display.py` uses `print_news()` to print the section, dates, descriptions,
  and URL fallback without making API requests or reading secrets.

### Important Python and API concepts
- **Dictionaries and lists:** the JSON response contains a list of article
  dictionaries; `news.py` converts each one to the small internal structure
  `title`, `source`, `published_at`, `description`, and `url`.
- **Functions:** each function has one job, such as cleaning text,
  formatting dates, standardising an article, or removing duplicates.
- **`try/except`:** network failures, timeouts, bad HTTP status codes, and
  malformed JSON return an unavailable result instead of crashing the app.
- **Environment variables:** the API key is read with
  `os.environ.get("MARKETAUX_API_KEY")`; the key is never written in source,
  README, tests, or output. In Replit, add it through Replit Secrets.
- **HTTP requests and JSON:** a request sends an endpoint, parameters, and
  an API key; the HTTP status and JSON response must both be validated.
  A timeout prevents a slow external service from blocking the whole report.
- **Datetime parsing:** an ISO/UTC timestamp such as
  `2026-09-02T14:32:17Z` becomes `2 Sep 2026`; malformed dates become
  `Date unavailable`.
- **Marketaux `match_score`:** this is the provider's deterministic estimate
  of how strongly an entity is associated with an article. A ticker association
  alone is not enough because broad market stories can mention many companies
  incidentally.
- **Optional values:** missing descriptions, publishers, dates, and URLs
  are kept missing and displayed with a concise fallback rather than being
  replaced with invented content.
- **Rate limits:** Marketaux limits requests on some plans, so one normal
  ticker lookup makes only one news request and tests use fake responses.

### Relevance, recency, duplicates, and hyperlinks
The request uses these documented Marketaux parameters:

```text
symbols=<TICKER>
filter_entities=true
must_have_entities=true
min_match_score=50.0
language=en
limit=3
published_after=<UTC time 14 days ago>
sort=entity_match_score
sort_order=desc
group_similar=true
```

The old `sort=published_desc` value was not a documented Marketaux option.
The request now keeps results recent with a rolling 14-day `published_after`
window, then ranks the remaining results by `entity_match_score` descending.
This is a deliberate trade-off: a shorter window improves recency but may
return fewer articles, while score filtering rejects broad market stories
instead of filling all three slots with weak matches.

`MIN_RELEVANCE_MATCH_SCORE = 50.0` is a clearly named v1 heuristic. The
documentation examples include body-only associations around 10–40 and strong
company-focused/title associations above 50, so this threshold is intended
to reject incidental mentions while retaining stronger company stories. It
can be tuned later if more real responses justify a change.

The local filter requires an exact entity symbol match and a numeric
`match_score` at or above the threshold. Missing scores are rejected safely.
If Marketaux includes an entity list, the app does not match ambiguous ticker
letters in headline text. Repeated URLs and normalised headlines are removed
locally.

When the terminal supports OSC-8 hyperlinks, `format_news_headline()` wraps
the visible headline in a terminal link escape sequence. Otherwise the
headline remains plain text and its original URL is printed beneath it.
An article with no valid URL is still displayed without a broken link.

### Defensive programming and testing
The output distinguishes an unavailable service from a successful empty
response: `Recent news temporarily unavailable.` versus
`No recent company-specific news found.`. A malformed individual article is
skipped while other valid articles remain visible.

`tests/test_news.py` uses mocked `requests.get()` responses. This tests valid
responses, fewer than three articles, empty data, missing keys, HTTP errors,
timeouts, malformed JSON, missing fields, duplicates, dates, hyperlinks, and
fallback output without using the daily Marketaux allowance.

---

## Feature 9 — Grounded AI Analysis

### What it does

Feature 9 adds an interpretation layer after the normal Features 1–8 report.
It does not become another financial-data source. Instead, it sends a compact
structured evidence package to Gemini and asks for neutral, selective
interpretation of the relationships in that evidence.

```text
Features 1–8 collect and calculate evidence
              ↓
analysis.py builds a compact context
              ↓
gemini_provider.py sends the context to Gemini
              ↓
validated structured analysis
              ↓
display.py prints the AI ANALYSIS section
```

### Grounding and safety rules

- Gemini receives only the evidence assembled from the existing application
  results; it does not call yfinance or Marketaux itself.
- The instruction prompt says not to invent company facts, financial figures,
  news, analyst forecasts, or peer metrics.
- Missing values remain `None` or unavailable; they are never changed to zero
  or the string `N/A` before being sent to Gemini.
- The output is required to use JSON structured output with six narrative
  sections and a list of key factors to watch.
- The result is validated before it reaches `display.py`; malformed or empty
  output is treated as unavailable.
- The feature deliberately avoids Buy/Hold/Sell recommendations, personalized
  advice, sentiment scoring, and unsupported price targets.

### Main files and responsibilities

- `investment_research/analysis.py` converts the existing Feature 1–8
  dictionaries into a compact JSON-safe context. The Feature 7 pandas
  DataFrame is flattened into nested dictionaries, and retrieval metadata is
  excluded.
- `investment_research/gemini_provider.py` is the only module that imports the
  Google Gemini SDK. It reads `GOOGLE_API_KEY`, uses `gemini-3.6-flash`, sends
  the grounding instructions, requests `application/json`, and validates the
  response.
- `investment_research/main.py` assembles the context from values it has
  already fetched and calls Feature 9 last. Provider failures cannot hide the
  earlier report.
- `investment_research/display.py` formats the structured sections and key
  factors; it never prints raw JSON or provider errors.

### Beginner concepts

- **LLM API:** a network service that accepts instructions and text and returns
  generated language.
- **Gemini API:** Google's model service used here for synthesis, not for
  retrieving the company's financial data.
- **Grounding:** limiting factual claims to the evidence included in the
  request.
- **Analysis context:** the small normalized dictionary passed to the model.
  Compact context reduces noise and makes the model's evidence boundary clear.
- **Tokens:** roughly the chunks of text a language model processes; shorter,
  focused context is easier for the model to handle.
- **Structured output:** JSON with known fields instead of an unpredictable
  essay, which lets the application validate the response before display.
- **Provider isolation:** if Claude or OpenAI is added later, the provider
  integration can be replaced or extended without rewriting data collection,
  context construction, or terminal formatting.

### Testing

`tests/test_analysis.py` uses mocked provider responses only. It covers context
construction, missing values, missing API keys, successful structured output,
provider failures, malformed/empty responses, display success, and display
fallback behavior. No live Gemini request is made by the automated tests.

---

### How the long yfinance company description was shortened
- The original description remains available in the data returned by the fetcher.
- Display uses a deterministic function `shorten_description()` in `display.py` that:
  1. Cleans whitespace.
  2. Splits sentences using a simple regex.
  3. Keeps the first 3–4 sentences up to a character limit and wraps them for the terminal.
 - No AI is used for description shortening — the method is deterministic and explainable.

---

# Feature 7 — Peer Comparison (Documentation)

- The first implementation uses a manual peer map in `investment_research/peers.py`:

```python
PEERS = {
    "NVDA": ["AMD", "AVGO", "INTC"],
    "AAPL": ["MSFT", "GOOGL", "AMZN"],
    "JPM":  ["BAC", "WFC", "C"],
    "NFLX": ["DIS", "CMCSA", "PARA"],
}
```

- It compares the target and each peer on the metrics listed above, displaying a compact terminal table and a 1–2 sentence rule-based factual summary (for example, which company has the highest revenue growth).
- The implementation intentionally does NOT calculate peer medians, averages, or rankings beyond the simple factual statements. It is designed as a focused comparison tool rather than a peer-universe analysis.

---

(End of Learning Guide)

