# Investment Research Assistant

A Python console application that looks up stock information — company name,
share price, and market capitalisation — using the yfinance library.

See `README.md` for the full project description, roadmap, and usage guide.

## How to Run

```bash
python run.py
```

## Project Structure

```
run.py                          ← Entry point. Run this to start the app.
investment_research/
  __init__.py                   ← Marks the folder as a Python package.
  main.py                       ← Application loop and user interaction.
  fetcher.py                    ← Fetches data from Yahoo Finance via yfinance.
  display.py                    ← Formats and prints results to the terminal.
README.md                       ← Full project documentation and roadmap.
requirements.txt                ← Python dependencies (pip install -r requirements.txt).
.gitignore                      ← Files excluded from version control.
```

## Stack

- Python 3 (standard library + yfinance)
- No web server, no database, no JavaScript

## Dependencies

- `yfinance` — installed in `.pythonlibs/` by Replit automatically

## User Preferences

- Long-term learning project — keep everything simple, modular, and well commented.
- Python only for now. No JavaScript, no web UI yet.
- No AI features in the first version.
- Every file should be clearly explained for a learner.
- Grow the project in small, deliberate phases (see README.md roadmap).

## Gotchas

- Run `python run.py` from the repository root, not from inside `investment_research/`.
- The relative imports (`from . import fetcher`) only work because `run.py` imports
  from `investment_research` as a package. Do not run `python investment_research/main.py`
  directly — it will raise an ImportError.
