"""Execute the P2.1A first scored acceptance through the oracle-firewalled harness."""

from __future__ import annotations

import sys
from pathlib import Path

# Direct script invocation sets ``sys.path[0]`` to ``scripts/``.  The harness
# lives under the backend package root, so make that execution root explicit.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.acceptance.p2_1.runner import main


if __name__ == "__main__":
    raise SystemExit(main())
