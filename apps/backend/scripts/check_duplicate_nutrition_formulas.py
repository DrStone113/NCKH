"""Reject approved nutrition formulas copied outside canonical/legacy locations.

The scanner intentionally uses semantic context (for example a ``bmi`` symbol
next to a comparison) instead of banning isolated numbers. This keeps food
composition, layout dimensions, timeouts, and exercise values distinguishable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


BACKEND = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "services").is_dir() and (parent / "tests").is_dir()
)
REPO = (
    BACKEND.parent.parent
    if (BACKEND.parent.parent / "apps" / "backend").resolve() == BACKEND.resolve()
    else BACKEND
)
MOBILE_LIB = (
    REPO / "apps/mobile/lib"
    if (REPO / "apps/mobile/lib").is_dir()
    else BACKEND / "__mobile_source_not_mounted__"
)

_SCAN_ROOTS = (
    BACKEND / "config.py",
    BACKEND / "modules",
    BACKEND / "services",
    MOBILE_LIB,
)
_EXTENSIONS = frozenset({".py", ".dart", ".json", ".yaml", ".yml", ".toml"})
_ALLOWED_PREFIXES = (
    BACKEND / "services/nutrition",
    BACKEND / "services/experiment/legacy_nutrition.py",
    MOBILE_LIB / "models/canonical_nutrition.dart",
)


@dataclass(frozen=True, slots=True)
class DuplicateFormula:
    path: Path
    line: int
    rule: str


_RULES = {
    "BMI_THRESHOLD_COPY": re.compile(
        r"(?im)(?:\bbmi\b[^\n]{0,100}(?:<|<=|>|>=)\s*(?:18\.5|23(?:\.0)?|25(?:\.0)?|30(?:\.0)?)"
        r"|(?:18\.5|23(?:\.0)?|25(?:\.0)?|30(?:\.0)?)\s*(?:<|<=|>|>=)[^\n]{0,100}\bbmi\b)"
    ),
    "BMI_BOUNDARY_TABLE_COPY": re.compile(
        r"(?is)\b(?:bmi|boundar(?:y|ies)|cutoffs?)\b.{0,160}18\.5.{0,80}23(?:\.0)?.{0,80}25(?:\.0)?.{0,80}30(?:\.0)?"
    ),
    "MIFFLIN_COPY": re.compile(
        r"(?is)(?:6\.25\s*\*\s*(?:height|height_cm)|(?:height|height_cm)\s*\*\s*6\.25).{0,180}(?:161|\+\s*5)"
    ),
    "ACTIVITY_FACTOR_TABLE_COPY": re.compile(
        r"(?is)1\.2.{0,100}1\.375.{0,100}1\.55.{0,100}1\.725.{0,100}1\.9"
    ),
    "FLUID_33MLKG_COPY": re.compile(
        r"(?i)(?:\bweight(?:_kg)?\b\s*\*\s*(?:0\.033|33(?:\.0)?)|(?:0\.033|33(?:\.0)?)\s*\*\s*\bweight(?:_kg)?\b)"
    ),
    "FIXED_TDEE_ADJUSTMENT_COPY": re.compile(
        r"(?i)\btdee\b\s*[+-]\s*(?:300|500)(?:\.0)?\b"
    ),
    "LOW_ENERGY_CLAMP_COPY": re.compile(
        r"(?i)\b(?:max|min)\s*\([^\n]{0,80}\b(?:1200|1500)(?:\.0)?\b"
    ),
}


def _is_allowed(path: Path) -> bool:
    resolved = path.resolve()
    return any(
        resolved == allowed.resolve()
        if allowed.is_file()
        else allowed.resolve() in resolved.parents
        for allowed in _ALLOWED_PREFIXES
    )


def production_files(roots: Iterable[Path] = _SCAN_ROOTS) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            if root.suffix in _EXTENSIONS:
                yield root
            continue
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and path.suffix in _EXTENSIONS:
                    yield path


def find_duplicate_formulas(paths: Iterable[Path]) -> list[DuplicateFormula]:
    findings: list[DuplicateFormula] = []
    for path in paths:
        if _is_allowed(path):
            continue
        text = path.read_text(encoding="utf-8")
        for rule, pattern in _RULES.items():
            for match in pattern.finditer(text):
                findings.append(
                    DuplicateFormula(
                        path=path,
                        line=text.count("\n", 0, match.start()) + 1,
                        rule=rule,
                    )
                )
    return findings


def main() -> int:
    findings = find_duplicate_formulas(production_files())
    for finding in findings:
        print(f"{finding.path.relative_to(REPO)}:{finding.line}:{finding.rule}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
