"""P2.2 lifecycle regressions for the single authoritative state machine."""

from __future__ import annotations

from services.plan_engine.contracts import PlanLifecycleStatus
from services.plan_engine.lifecycle import LIFECYCLE_TRANSITIONS, transition_allowed, valid_targets


def test_paused_to_active_is_the_only_valid_resume_transition():
    assert transition_allowed(PlanLifecycleStatus.PAUSED, PlanLifecycleStatus.ACTIVE)
    assert not transition_allowed(PlanLifecycleStatus.ACTIVE, PlanLifecycleStatus.ACTIVE)
    assert not transition_allowed(PlanLifecycleStatus.CANCELLED, PlanLifecycleStatus.ACTIVE)
    assert not transition_allowed(PlanLifecycleStatus.COMPLETED, PlanLifecycleStatus.ACTIVE)
    assert not transition_allowed(PlanLifecycleStatus.SUPERSEDED, PlanLifecycleStatus.ACTIVE)


def test_authoritative_transition_table_covers_terminal_and_mutable_states():
    assert valid_targets(PlanLifecycleStatus.SAVED) == (
        PlanLifecycleStatus.ACTIVE,
        PlanLifecycleStatus.CANCELLED,
    )
    assert valid_targets(PlanLifecycleStatus.ACTIVE) == (
        PlanLifecycleStatus.PAUSED,
        PlanLifecycleStatus.COMPLETED,
        PlanLifecycleStatus.CANCELLED,
    )
    assert valid_targets(PlanLifecycleStatus.PAUSED) == (
        PlanLifecycleStatus.ACTIVE,
        PlanLifecycleStatus.COMPLETED,
        PlanLifecycleStatus.CANCELLED,
    )
    assert not valid_targets(PlanLifecycleStatus.CANCELLED)
    assert not valid_targets(PlanLifecycleStatus.COMPLETED)
    assert not valid_targets(PlanLifecycleStatus.SUPERSEDED)
    assert PlanLifecycleStatus.ACTIVE in LIFECYCLE_TRANSITIONS
