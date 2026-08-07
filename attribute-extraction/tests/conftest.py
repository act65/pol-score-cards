"""Make the extraction modules importable from `attribute-extraction/tests/`.

The modules are run as scripts from `attribute-extraction/` and import each
other by bare name, so put that directory on the path for the tests.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.abspath(os.path.join(HERE, ".."))
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)
