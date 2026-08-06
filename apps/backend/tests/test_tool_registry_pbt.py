"""
Property-based tests for ``ToolRegistry.validate``.

Task 2.2 — **Property 1: Tool registry validation**
**Validates: Requirements 1.1**

Three universal properties are exercised with ``hypothesis``:

1. ``validate(unknown_name, args)`` always returns ``(False, "UNKNOWN_TOOL")``,
   regardless of the args.
2. For a tool registered with a strict schema, calling ``validate`` with args
   that do not match the schema always returns ``(False, "INVALID_ARGS")``.
3. ``validate`` never raises an exception out to the caller — for every
   ``(name, args)`` pair, the call must return a ``(bool, str | None)`` tuple
   with one of the documented error codes.

These properties together encode the contract from
``backend/.kiro/specs/chatbot-redesign/design.md`` §9.2 and Requirement 1.1
in ``requirements.md`` ("Tool_Dispatcher SHALL trả về ToolResult(ok=false)
với error_code lần lượt là 'UNKNOWN_TOOL' hoặc 'INVALID_ARGS' và SHALL NOT
để exception thoát ra ngoài").
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

# Allow ``import services.agent.tool_registry`` when pytest is run from the
# ``backend/`` directory (matches the convention used in other backend tests).
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent.tool_registry import ToolDescriptor, ToolRegistry  # noqa: E402


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# JSON-compatible scalar / container values, used both as candidate ``args``
# and as nested values inside dicts. Kept intentionally small to avoid blowing
# up generation cost on a non-async PBT.
_json_scalar = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=20),
)

_json_value = st.recursive(
    _json_scalar,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=10), children, max_size=5),
    ),
    max_leaves=10,
)

# ``args`` for ``validate`` is intentionally any JSON value (not just dicts):
# the LLM can hallucinate non-dict shapes and the registry must reject them
# without raising.
_args_strategy: st.SearchStrategy[Any] = _json_value

# Tool names are arbitrary strings. We want to make sure ``validate`` rejects
# names that obviously don't exist; we filter to names that are not the one
# we register in the corresponding test below.
_name_strategy = st.text(min_size=0, max_size=30)


# A strict schema used by property 2: ``args`` must be an object with a
# required ``user_id`` string property and a numeric ``age`` ∈ [10, 120].
# Any deviation (wrong type, missing required, extra-strict bound) must yield
# ``"INVALID_ARGS"``.
_STRICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string", "minLength": 1},
        "age": {"type": "integer", "minimum": 10, "maximum": 120},
    },
    "required": ["user_id", "age"],
    "additionalProperties": False,
}


def _build_registry_with_strict_tool() -> ToolRegistry:
    """Build a registry containing a single tool with ``_STRICT_SCHEMA``."""
    registry = ToolRegistry()
    registry.register(
        ToolDescriptor(
            name="strict_tool",
            description="Tool used by PBT to exercise schema validation.",
            parameters_schema=_STRICT_SCHEMA,
            side="server",
            fn=lambda **kwargs: kwargs,
            idempotent=True,
        )
    )
    return registry


def _matches_strict_schema(args: Any) -> bool:
    """Pure Python predicate mirroring ``_STRICT_SCHEMA``.

    Used to ``assume()`` away the (very small) chance that a randomly
    generated value happens to be a valid instance of the schema. Keeping
    this predicate explicit (instead of round-tripping through ``jsonschema``)
    makes the property test independent of the implementation under test.
    """
    if not isinstance(args, dict):
        return False
    if set(args.keys()) - {"user_id", "age"}:
        return False
    if "user_id" not in args or "age" not in args:
        return False
    user_id = args["user_id"]
    age = args["age"]
    if not isinstance(user_id, str) or len(user_id) < 1:
        return False
    # ``bool`` is a subclass of ``int`` in Python; jsonschema treats booleans
    # as not being valid integers, so we mirror that behavior here.
    if isinstance(age, bool) or not isinstance(age, int):
        return False
    if age < 10 or age > 120:
        return False
    return True


# ---------------------------------------------------------------------------
# Property 1.a — unknown tool
# ---------------------------------------------------------------------------


@given(name=_name_strategy, args=_args_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_validate_unknown_tool_returns_unknown_tool(name: str, args: Any) -> None:
    """``validate(unknown_name, _)`` always returns ``(False, "UNKNOWN_TOOL")``.

    We start from an empty registry, then optionally register an unrelated
    tool, and finally call ``validate(name, args)`` with a name guaranteed to
    differ from any registered tool. The outcome must be exactly the unknown
    tool sentinel — never ``(False, "INVALID_ARGS")``, never an exception.
    """
    registry = _build_registry_with_strict_tool()
    # Ensure the generated name is different from the one tool we registered.
    assume(name != "strict_tool")

    ok, err = registry.validate(name, args)

    assert ok is False
    assert err == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# Property 1.b — invalid args for a registered tool
# ---------------------------------------------------------------------------


@given(args=_args_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_validate_invalid_args_returns_invalid_args(args: Any) -> None:
    """For a registered tool, args that do not match the schema → ``"INVALID_ARGS"``.

    We discard the (rare) cases where the generated ``args`` happens to be a
    valid instance of ``_STRICT_SCHEMA``. For every other input the registry
    must answer ``(False, "INVALID_ARGS")``.
    """
    registry = _build_registry_with_strict_tool()
    assume(not _matches_strict_schema(args))

    ok, err = registry.validate("strict_tool", args)

    assert ok is False
    assert err == "INVALID_ARGS"


# ---------------------------------------------------------------------------
# Property 1.c — validate never raises and always returns a documented tuple
# ---------------------------------------------------------------------------


_VALID_ERR_CODES = {None, "UNKNOWN_TOOL", "INVALID_ARGS"}


@given(name=_name_strategy, args=_args_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_validate_never_raises(name: str, args: Any) -> None:
    """``validate`` must not raise for any ``(name, args)`` pair.

    The dispatcher relies on this guarantee to convert validation failures
    into ``ToolResult(ok=False)`` without leaking exceptions to the agent
    loop (Requirement 1.1).
    """
    registry = _build_registry_with_strict_tool()

    try:
        result = registry.validate(name, args)
    except Exception as exc:  # pragma: no cover — fails the property
        pytest.fail(f"validate raised {type(exc).__name__}: {exc!r}")

    assert isinstance(result, tuple)
    assert len(result) == 2
    ok, err = result
    assert isinstance(ok, bool)
    assert err in _VALID_ERR_CODES
    # Cross-check the (ok, err) shape: success ⇔ err is None.
    assert (ok is True) == (err is None)
