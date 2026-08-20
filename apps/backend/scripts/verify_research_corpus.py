"""Verify the frozen research corpus against its file and database manifest."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from services.experiment.config import ExperimentConfig
from services.experiment.corpus import (
    DEFAULT_MANIFEST_PATH,
    ResearchCorpusManifest,
    verify_research_corpus,
)
from services.experiment.errors import ExperimentError


def _parser() -> argparse.ArgumentParser:
    defaults = ExperimentConfig(condition="C")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--corpus-version", default=defaults.corpus_version)
    parser.add_argument("--corpus-hash", default=defaults.corpus_hash)
    return parser


async def _run(args: argparse.Namespace) -> int:
    try:
        file_manifest = ResearchCorpusManifest.model_validate_json(
            args.manifest.read_text(encoding="utf-8")
        )
        if file_manifest.corpus_version != args.corpus_version:
            raise ExperimentError("EXPERIMENT_CORPUS_VERSION_MISMATCH")
        if file_manifest.corpus_hash != args.corpus_hash:
            raise ExperimentError("EXPERIMENT_CORPUS_HASH_MISMATCH")
        db_manifest = await verify_research_corpus(
            expected_version=args.corpus_version,
            expected_hash=args.corpus_hash,
        )
        if db_manifest != file_manifest:
            raise ExperimentError("EXPERIMENT_MANIFEST_FILE_DB_MISMATCH")
    except (OSError, ValidationError, ExperimentError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "corpus_version": db_manifest.corpus_version,
                "corpus_hash": db_manifest.corpus_hash,
                "manifest_hash": db_manifest.manifest_hash,
                "chunks": db_manifest.inserted_chunk_count,
                "embeddings": db_manifest.embedding_count,
                "dynamic_rows": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
