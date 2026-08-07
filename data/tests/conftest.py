"""Make the modules under test importable from `data/tests/`.

The pipeline modules live in `data/` and `data/scrapers/` and are run as scripts
from their own directories, so they import each other by bare name. Rather than
turn them into a package (which would change how every CLI is invoked), put both
directories on the path for the tests.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for path in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "scrapers")):
    resolved = os.path.abspath(path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)
