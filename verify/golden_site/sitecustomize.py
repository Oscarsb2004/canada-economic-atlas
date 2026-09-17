"""
Imported automatically by Python at start-up, but only for processes the
golden-master harness launches: `verify/golden.py` puts this folder on
PYTHONPATH and sets GOLDEN_MODE. A normal run never has this folder on its path.
"""

import os

if os.environ.get("GOLDEN_MODE"):
    import golden_io

    golden_io.install()
