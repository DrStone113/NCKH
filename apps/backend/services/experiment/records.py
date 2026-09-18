"""JSONL run records and source-control metadata for research mode."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services.experiment.errors import ExperimentError, safe_error_detail


class ExperimentRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "2.0"
    experiment_id: str
    run_id: str
    condition: str
    protocol_id: str | None = None
    benchmark_version: str | None = None
    benchmark_file_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    benchmark_manifest_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    benchmark_case_hash: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    benchmark_split: str | None = None
    batch_schedule_seed: int | None = None
    repetition_index: int | None = Field(default=None, ge=1)
    schedule_index: int | None = Field(default=None, ge=1)
    test_case_id: str
    timestamp: str
    config: dict[str, Any]
    config_hash: str
    user_query: str
    profile_snapshot_or_null: dict[str, Any] | None
    rendered_system_prompt: str
    model_requested: str
    model_actual: str | None
    temperature: float
    seed: int
    tools_offered: list[str]
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_trace: dict[str, Any] | None = None
    token_usage: dict[str, int] | None = None
    completion_finish_reasons: list[str | None] = Field(default_factory=list)
    final_response: str
    latency_ms: float
    error: str | None
    git_commit: str | None
    worktree_clean: bool | None


def repository_state(repo_root: Path) -> tuple[str | None, bool | None]:
    """Read commit/dirty state without invoking a shell or changing git state."""

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        return commit or None, not bool(status.strip())
    except Exception:
        return None, None


def append_jsonl(path: Path, record: ExperimentRunRecord) -> None:
    """Append one canonical UTF-8 JSON object followed by a newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                record.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        handle.write("\n")


def load_jsonl_records(path: Path) -> tuple[ExperimentRunRecord, ...]:
    """Load a complete JSONL record sequence and reject partial/tampered rows."""

    if not path.exists():
        return ()
    records: list[ExperimentRunRecord] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ExperimentError(
                        "EXPERIMENT_BATCH_RESUME_BLANK_LINE", str(line_number)
                    )
                try:
                    records.append(ExperimentRunRecord.model_validate_json(line))
                except (ValidationError, ValueError) as exc:
                    raise ExperimentError(
                        "EXPERIMENT_BATCH_RESUME_RECORD_INVALID",
                        f"line={line_number}; {safe_error_detail(exc)}",
                    ) from exc
    except ExperimentError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ExperimentError(
            "EXPERIMENT_BATCH_RESUME_FILE_INVALID", safe_error_detail(exc)
        ) from exc
    return tuple(records)


RepositoryStateProbe = Callable[[], tuple[str | None, bool | None]]


__all__ = [
    "ExperimentRunRecord",
    "RepositoryStateProbe",
    "append_jsonl",
    "load_jsonl_records",
    "repository_state",
]
