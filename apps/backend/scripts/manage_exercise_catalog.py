"""Write or verify the deterministic E2 canonical exercise manifest.

Examples:
    py -3.10 scripts/manage_exercise_catalog.py --write-manifest
    py -3.10 scripts/manage_exercise_catalog.py --verify
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from modules.wger.canonical_exercises import (  # noqa: E402
    MANIFEST_FILE,
    CanonicalExerciseError,
    build_catalog_manifest,
    verify_catalog_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write-manifest", action="store_true")
    action.add_argument("--verify", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.write_manifest:
            manifest = build_catalog_manifest()
            MANIFEST_FILE.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            result = {
                "ok": True,
                "action": "manifest_written",
                "catalog_version": manifest["schema_version"],
                "records": manifest["catalog"]["record_count"],
                "catalog_sha256": manifest["catalog"]["content_sha256"],
            }
        else:
            result = verify_catalog_manifest()
            result["action"] = "manifest_verified"
    except (CanonicalExerciseError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
