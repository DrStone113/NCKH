"""Authoritative lifecycle rules for immutable Plan V2 revisions.

The lifecycle is deliberately defined once.  Memory previews, PostgreSQL
persistence, HTTP handlers, and UI affordances may ask this module whether a
transition is valid; none of them owns an independent transition map.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .contracts import PlanLifecycleStatus


# The key is the requested target state and the value is the set of allowed
# current states.  Terminal states deliberately have no outgoing transition.
LIFECYCLE_TRANSITIONS: Final[Mapping[PlanLifecycleStatus, frozenset[PlanLifecycleStatus]]] = {
    PlanLifecycleStatus.ACTIVE: frozenset({
        PlanLifecycleStatus.SAVED,
        PlanLifecycleStatus.PAUSED,
    }),
    PlanLifecycleStatus.PAUSED: frozenset({PlanLifecycleStatus.ACTIVE}),
    PlanLifecycleStatus.COMPLETED: frozenset({
        PlanLifecycleStatus.ACTIVE,
        PlanLifecycleStatus.PAUSED,
    }),
    PlanLifecycleStatus.CANCELLED: frozenset({
        PlanLifecycleStatus.DRAFT,
        PlanLifecycleStatus.PENDING_CONFIRMATION,
        PlanLifecycleStatus.SAVED,
        PlanLifecycleStatus.ACTIVE,
        PlanLifecycleStatus.PAUSED,
    }),
}


def transition_allowed(current: PlanLifecycleStatus, target: PlanLifecycleStatus) -> bool:
    """Return whether an explicit lifecycle command is valid.

    Idempotency is intentionally handled by the repository before this rule:
    retrying the *same* completed action returns its stored result, whereas a
    new request to transition an already ACTIVE revision to ACTIVE is invalid.
    """

    return current in LIFECYCLE_TRANSITIONS.get(target, frozenset())


def valid_targets(current: PlanLifecycleStatus) -> tuple[PlanLifecycleStatus, ...]:
    """Expose stable UI/API affordances without duplicating state rules."""

    return tuple(target for target, sources in LIFECYCLE_TRANSITIONS.items() if current in sources)


__all__ = ["LIFECYCLE_TRANSITIONS", "transition_allowed", "valid_targets"]
