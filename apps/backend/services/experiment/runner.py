"""Single-case isolated research experiment runner."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from services.experiment.config import ExperimentConfig
from services.experiment.context import assemble_research_context
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.llm import ResearchCompletionClient, execute_fixed_agent
from services.experiment.models import ExperimentTestCase
from services.experiment.rag import ResearchRagProvider
from services.experiment.records import (
    ExperimentRunRecord,
    RepositoryStateProbe,
    repository_state,
)
from services.experiment.tools import build_research_tool_registry


def _default_repo_probe() -> tuple[str | None, bool | None]:
    repo_root = Path(__file__).resolve().parents[4]
    return repository_state(repo_root)


class ResearchExperimentRunner:
    """Execute exactly one explicit test case without production chat state."""

    def __init__(
        self,
        *,
        completion_client: ResearchCompletionClient,
        rag_provider: ResearchRagProvider | None = None,
        repository_probe: RepositoryStateProbe = _default_repo_probe,
    ) -> None:
        self.completion_client = completion_client
        self.rag_provider = rag_provider
        self.repository_probe = repository_probe

    async def run(
        self,
        *,
        experiment_id: str,
        config: ExperimentConfig,
        test_case: ExperimentTestCase,
    ) -> ExperimentRunRecord:
        timestamp = datetime.now(timezone.utc).isoformat()
        run_id = str(uuid4())
        git_commit, worktree_clean = self.repository_probe()

        # Cold model load is an environment setup cost, not treatment latency.
        # Preserve any failure for the durable record and never fall back to B.
        prewarm_error: ExperimentError | None = None
        if config.rag_enabled:
            if self.rag_provider is None:
                prewarm_error = ExperimentError("EXPERIMENT_CORPUS_NOT_READY")
            else:
                try:
                    await self.rag_provider.prewarm()
                except ExperimentError as exc:
                    prewarm_error = exc
                except Exception as exc:
                    prewarm_error = ExperimentError(
                        "EXPERIMENT_EMBEDDING_PREWARM_FAILED",
                        safe_error_detail(exc),
                    )

        started = time.perf_counter()

        profile_snapshot = (
            test_case.profile.model_dump(mode="json")
            if config.profile_enabled
            else None
        )
        rendered_system_prompt = ""
        model_actual: str | None = None
        final_response = ""
        tool_calls: list[dict] = []
        retrieval_trace: dict | None = None
        token_usage: dict[str, int] | None = None
        error: str | None = None
        registry = build_research_tool_registry(config)

        try:
            if prewarm_error is not None:
                raise prewarm_error
            rag_chunks = None
            if config.rag_enabled:
                if self.rag_provider is None:
                    raise ExperimentError("EXPERIMENT_CORPUS_NOT_READY")
                trace = await self.rag_provider.retrieve(
                    test_case.user_query, config
                )
                retrieval_trace = trace.model_dump(mode="json")
                rag_chunks = trace.chunks

            context = assemble_research_context(
                config=config,
                user_query=test_case.user_query,
                profile=test_case.profile,
                rag_chunks=rag_chunks,
                tool_registry=registry,
            )
            rendered_system_prompt = context.rendered_system_prompt
            result = await execute_fixed_agent(
                client=self.completion_client,
                initial_messages=context.messages,
                tool_schemas=context.tool_schemas,
                tool_registry=registry,
                config=config,
            )
            model_actual = result.model_actual
            final_response = result.final_response
            tool_calls = list(result.tool_calls)
            token_usage = result.token_usage
        except ExperimentError as exc:
            error = str(exc)
        except Exception as exc:  # defensive boundary for a durable run record
            error = f"EXPERIMENT_RUN_FAILED: {safe_error_detail(exc)}"

        return ExperimentRunRecord(
            experiment_id=experiment_id,
            run_id=run_id,
            condition=config.condition,
            protocol_id=config.protocol_id,
            test_case_id=test_case.test_case_id,
            timestamp=timestamp,
            config=config.serialize(),
            config_hash=config.config_hash(),
            user_query=test_case.user_query,
            profile_snapshot_or_null=profile_snapshot,
            rendered_system_prompt=rendered_system_prompt,
            model_requested=config.model,
            model_actual=model_actual,
            temperature=config.temperature,
            seed=config.seed,
            tools_offered=registry.names(),
            tool_calls=tool_calls,
            retrieval_trace=retrieval_trace,
            token_usage=token_usage,
            final_response=final_response,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            error=error,
            git_commit=git_commit,
            worktree_clean=worktree_clean,
        )


__all__ = ["ResearchExperimentRunner"]
