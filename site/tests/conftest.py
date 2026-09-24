"""Make `site/app.py` importable from `site/tests/`, against a temp dataset.

The Flask app reads its JSONL dataset at import time from $SCORECARD_DATA, so
the variable has to be set before the import — and to an ABSOLUTE path, because
the default ("static") is relative to site/ and the root `pytest` run has the
repo root as its working directory. Setting it here rather than chdir()-ing
keeps this suite from moving the cwd out from under data/tests and game.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.abspath(os.path.join(HERE, ".."))
if SITE not in sys.path:
    sys.path.insert(0, SITE)
os.environ.setdefault("SCORECARD_DATA", os.path.join(SITE, "static"))
