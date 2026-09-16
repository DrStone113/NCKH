"""Isolated infrastructure for controlled research experiments.

This package deliberately does not import the production chat orchestrator,
memory service, turn router, or production tool registry.
"""

from services.experiment.config import (
    NUTRITION_ABLATION_ARMS,
    NUTRITION_ABLATION_PROTOCOL_ID,
    ExperimentConfig,
)
from services.experiment.models import ExperimentProfile, ExperimentTestCase
from services.experiment.runner import ResearchExperimentRunner

__all__ = [
    "ExperimentConfig",
    "ExperimentProfile",
    "ExperimentTestCase",
    "NUTRITION_ABLATION_ARMS",
    "NUTRITION_ABLATION_PROTOCOL_ID",
    "ResearchExperimentRunner",
]
