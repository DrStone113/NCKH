"""Run the Plan V2 Confirmatory V3 development smoke or one-shot final run."""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.acceptance.v3.runner import main


if __name__ == "__main__":
    raise SystemExit(main())
