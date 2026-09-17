"""Isolated infrastructure for controlled research experiments.

This package deliberately does not import the production chat orchestrator,
memory service, turn router, or production tool registry.
"""

from typing import TYPE_CHECKING, Any

from services.experiment.config import (
    NUTRITION_ABLATION_ARMS,
    NUTRITION_ABLATION_MODEL,
    NUTRITION_ABLATION_PROTOCOL_ID,
    ExperimentConfig,
)
from services.experiment.models import ExperimentProfile, ExperimentTestCase

if TYPE_CHECKING:
    from services.experiment.batch import NutritionAblationBatchRunner
    from services.experiment.runner import ResearchExperimentRunner


def __getattr__(name: str) -> Any:
    """Keep convenience exports without importing the full tool graph eagerly."""

    if name == "NutritionAblationBatchRunner":
        from services.experiment.batch import NutritionAblationBatchRunner

        return NutritionAblationBatchRunner
    if name == "ResearchExperimentRunner":
        from services.experiment.runner import ResearchExperimentRunner

        return ResearchExperimentRunner
    raise AttributeError(name)

__all__ = [
    "ExperimentConfig",
    "ExperimentProfile",
    "ExperimentTestCase",
    "NUTRITION_ABLATION_ARMS",
    "NUTRITION_ABLATION_MODEL",
    "NUTRITION_ABLATION_PROTOCOL_ID",
    "NutritionAblationBatchRunner",
    "ResearchExperimentRunner",
]
