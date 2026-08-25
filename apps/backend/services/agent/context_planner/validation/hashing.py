"""Canonical hashing and frozen-artifact verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .contracts import DatasetIdentity


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def files_sha256(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=str):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verify_frozen_payload(identity: DatasetIdentity, cases: Any, oracles: Any) -> None:
    if not identity.eligible_for_independent_evaluation:
        raise ValueError("dataset is not frozen, human-reviewed, independent validation")
    actual_content = content_sha256(cases)
    actual_oracle = content_sha256(oracles)
    if actual_content != identity.content_sha256:
        raise ValueError("validation dataset content hash mismatch")
    if actual_oracle != identity.oracle_sha256:
        raise ValueError("validation oracle hash mismatch")


__all__ = ["canonical_json_bytes", "content_sha256", "files_sha256", "verify_frozen_payload"]
