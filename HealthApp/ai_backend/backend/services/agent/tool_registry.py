"""Tool registry and descriptor for the agent tool catalog.

This module implements ``ToolDescriptor`` (metadata for a single tool) and
``ToolRegistry`` (an in-memory map ``tool_name -> ToolDescriptor``) used by the
agent orchestrator and the tool dispatcher.

Design references:
- ``backend/.kiro/specs/chatbot-redesign/design.md`` §4.3 (Components),
  §9.2 (ToolRegistry contract), §5 (Tool catalog).
- Requirements 1.1, 2.3, 2.4, 2.5 in
  ``backend/.kiro/specs/chatbot-redesign/requirements.md``.

Schema output follows the Ollama / OpenAI function-calling convention::

    {
        "type": "function",
        "function": {
            "name": "...",
            "description": "...",
            "parameters": { /* JSON Schema */ },
        },
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import jsonschema
from jsonschema.exceptions import SchemaError, ValidationError

ToolSide = Literal["server", "client"]

# Default timeout per tool invocation, used when a descriptor does not override
# it. Matches ``TOOL_TIMEOUT`` in design.md §11.1.
DEFAULT_TOOL_TIMEOUT_MS = 15_000


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """Metadata describing a single tool available to the agent.

    Parameters
    ----------
    name:
        Unique tool name used by the LLM to invoke the tool.
    description:
        Short natural-language description shown to the LLM.
    parameters_schema:
        JSON Schema describing the ``arguments`` object for this tool.
    side:
        ``"server"`` if the tool runs in the FastAPI backend; ``"client"`` if
        the tool is dispatched over WebSocket to the Flutter client.
    fn:
        Implementation for server-side tools. ``None`` for client-side tools
        (their execution is delegated to the Flutter client and resolved via
        ``correlation_id`` matching).
    idempotent:
        ``True`` for read-only / pure tools whose repeated invocation with the
        same arguments yields semantically equivalent results. Write tools set
        this to ``False`` and must include ``request_id`` in their arguments
        (see design §5).
    timeout_ms:
        Per-call timeout enforced by the dispatcher.
    """

    name: str
    description: str
    parameters_schema: dict[str, Any]
    side: ToolSide
    fn: Callable[..., Any] | None = None
    idempotent: bool = True
    timeout_ms: int = DEFAULT_TOOL_TIMEOUT_MS


class ToolRegistry:
    """In-memory registry mapping ``tool_name -> ToolDescriptor``.

    The registry is populated at application startup (see
    ``services/agent/tools/__init__.py``) and consumed by the orchestrator,
    the dispatcher, and the LLM client (which forwards ``schemas()`` to
    Ollama as the ``tools`` field).
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDescriptor] = {}

    # ------------------------------------------------------------------ register
    def register(self, descriptor: ToolDescriptor) -> None:
        """Register ``descriptor``.

        Raises
        ------
        ValueError
            If a tool with the same name is already registered. This catches
            duplicate registrations early instead of silently shadowing.
        """
        if not isinstance(descriptor, ToolDescriptor):
            raise TypeError(
                f"register() expected ToolDescriptor, got {type(descriptor).__name__}"
            )
        if descriptor.name in self._tools:
            raise ValueError(f"Tool already registered: {descriptor.name!r}")
        self._tools[descriptor.name] = descriptor

    # ---------------------------------------------------------------------- get
    def get(self, name: str) -> ToolDescriptor | None:
        """Return descriptor for ``name`` or ``None`` if unknown."""
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        """Return tool names in insertion order (for diagnostics)."""
        return list(self._tools.keys())

    # ------------------------------------------------------------------ schemas
    def schemas(self) -> list[dict[str, Any]]:
        """Export tool schemas in Ollama function-calling format.

        Returned list is safe to pass directly as the ``tools`` field of an
        Ollama ``/api/chat`` call.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters_schema,
                },
            }
            for d in self._tools.values()
        ]

    # ----------------------------------------------------------------- validate
    def validate(
        self, name: str, args: Any
    ) -> tuple[bool, str | None]:
        """Validate ``args`` against the schema of tool ``name``.

        Contract (Requirement 1.1):

        - Returns ``(False, "UNKNOWN_TOOL")`` if no tool is registered with
          ``name``.
        - Returns ``(False, "INVALID_ARGS")`` if ``args`` does not conform to
          the tool's JSON Schema, or if the schema itself is malformed, or if
          any other error occurs during validation.
        - Returns ``(True, None)`` on success.

        This method MUST NOT raise. Any exception is caught and converted to
        ``(False, "INVALID_ARGS")`` so the dispatcher can convert the result
        into a ``ToolResult(ok=False)`` without leaking exceptions to the
        agent loop.
        """
        descriptor = self._tools.get(name)
        if descriptor is None:
            return False, "UNKNOWN_TOOL"

        try:
            jsonschema.validate(instance=args, schema=descriptor.parameters_schema)
        except ValidationError:
            return False, "INVALID_ARGS"
        except SchemaError:
            # Schema itself is malformed. Treat as invalid args from the
            # caller's perspective so the agent loop can recover gracefully.
            return False, "INVALID_ARGS"
        except Exception:
            # Catch-all defensive guard. ``validate`` MUST never raise.
            return False, "INVALID_ARGS"

        return True, None


__all__ = [
    "DEFAULT_TOOL_TIMEOUT_MS",
    "ToolDescriptor",
    "ToolRegistry",
    "ToolSide",
]
