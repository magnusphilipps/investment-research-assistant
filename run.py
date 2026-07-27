# ============================================================
# run.py — Entry Point
# ============================================================
#
# PURPOSE:
#   This is the file you run to start the application.
#   It contains as little code as possible — just enough to
#   launch the program.
#
# HOW TO RUN:
#   Open a terminal and type:
#       python run.py
#
# WHY A SEPARATE FILE?
#   Python has a special variable called __name__. When you run
#   a file directly (e.g. `python run.py`), Python sets
#   __name__ to the string "__main__". When a file is imported
#   by another file, __name__ is set to the module's name instead.
#
#   The `if __name__ == "__main__":` guard below ensures the app
#   only starts when you run this file directly — not when it's
#   imported as part of something else.
# ============================================================

from investment_research.main import run

if __name__ == "__main__":
    run()
