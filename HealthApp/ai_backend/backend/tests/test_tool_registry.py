"""Unit tests cho `services.agent.tool_registry`.

Task 2.3 (Validates: Requirements 2.3, 2.4, 2.5):

  - ``register()`` rồi ``get()`` trả về đúng descriptor (cùng object,
    cùng các field metadata).
  - ``schemas()`` xuất đúng format Ollama function-calling::

        {
          "type": "function",
          "function": {
            "name": "...",
            "description": "...",
            "parameters": { /* JSON Schema */ }
          }
        }

Các test này không phụ thuộc Postgres hoặc Ollama; chỉ exercise registry
in-memory.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Cho phép `import services.agent...` khi chạy `pytest` từ thư mục `backend/`.
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent.tool_registry import (  # noqa: E402
    DEFAULT_TOOL_TIMEOUT_MS,
    ToolDescriptor,
    ToolRegistry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _server_descriptor(
    name: str = "calculate_tdee",
    description: str = "Tính BMR và TDEE từ profile.",
    parameters_schema: dict | None = None,
    fn=None,
    idempotent: bool = True,
    timeout_ms: int = DEFAULT_TOOL_TIMEOUT_MS,
) -> ToolDescriptor:
    """Build a server-side descriptor with sensible defaults for tests."""
    if parameters_schema is None:
        parameters_schema = {
            "type": "object",
            "properties": {
                "age": {"type": "integer", "minimum": 10, "maximum": 120},
                "weight_kg": {"type": "number"},
            },
            "required": ["age", "weight_kg"],
            "additionalProperties": False,
        }
    if fn is None:
        def fn(args):  # pragma: no cover - exercised only when invoked
            return {"bmr": 1500, "tdee": 2000, "daily_kcal": 1800}
    return ToolDescriptor(
        name=name,
        description=description,
        parameters_schema=parameters_schema,
        side="server",
        fn=fn,
        idempotent=idempotent,
        timeout_ms=timeout_ms,
    )


def _client_descriptor(
    name: str = "log_meal",
    description: str = "Ghi bữa ăn trên client.",
    idempotent: bool = False,
) -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        description=description,
        parameters_schema={
            "type": "object",
            "properties": {
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                },
                "dish_name": {"type": "string"},
                "request_id": {"type": "string"},
            },
            "required": ["meal_type", "dish_name", "request_id"],
        },
        side="client",
        fn=None,
        idempotent=idempotent,
    )


# ---------------------------------------------------------------------------
# register / get
# ---------------------------------------------------------------------------


class TestRegisterAndGet:
    def test_get_returns_none_for_unknown_tool(self):
        registry = ToolRegistry()
        assert registry.get("__missing__") is None

    def test_register_then_get_returns_same_descriptor(self):
        """register() rồi get() trả về CHÍNH descriptor đã đăng ký."""
        registry = ToolRegistry()
        descriptor = _server_descriptor(name="calculate_tdee")

        registry.register(descriptor)
        fetched = registry.get("calculate_tdee")

        # Phải là cùng object (identity), không chỉ giống về giá trị.
        assert fetched is descriptor
        assert fetched.name == "calculate_tdee"
        assert fetched.side == "server"
        assert fetched.idempotent is True
        assert fetched.fn is descriptor.fn
        assert fetched.parameters_schema == descriptor.parameters_schema

    def test_register_preserves_all_metadata_fields(self):
        registry = ToolRegistry()
        descriptor = _server_descriptor(
            name="suggest_dish",
            description="Gợi ý món Việt theo macro.",
            idempotent=True,
            timeout_ms=8000,
        )

        registry.register(descriptor)
        fetched = registry.get("suggest_dish")

        assert fetched is not None
        assert fetched.description == "Gợi ý món Việt theo macro."
        assert fetched.timeout_ms == 8000

    def test_register_client_descriptor_with_fn_none(self):
        """Client tools không có ``fn`` (chạy trên Flutter)."""
        registry = ToolRegistry()
        descriptor = _client_descriptor(name="log_meal")

        registry.register(descriptor)
        fetched = registry.get("log_meal")

        assert fetched is not None
        assert fetched.side == "client"
        assert fetched.fn is None
        assert fetched.idempotent is False

    def test_register_multiple_tools_each_retrievable(self):
        registry = ToolRegistry()
        a = _server_descriptor(name="calculate_tdee")
        b = _server_descriptor(name="suggest_dish")
        c = _client_descriptor(name="log_meal")

        registry.register(a)
        registry.register(b)
        registry.register(c)

        assert registry.get("calculate_tdee") is a
        assert registry.get("suggest_dish") is b
        assert registry.get("log_meal") is c
        assert len(registry) == 3
        assert "calculate_tdee" in registry
        assert "log_meal" in registry
        assert "__missing__" not in registry

    def test_register_duplicate_name_raises(self):
        """Đăng ký trùng tên phải raise rõ ràng thay vì shadow âm thầm."""
        registry = ToolRegistry()
        registry.register(_server_descriptor(name="calculate_tdee"))

        with pytest.raises(ValueError, match="calculate_tdee"):
            registry.register(_server_descriptor(name="calculate_tdee"))

    def test_register_rejects_non_descriptor(self):
        registry = ToolRegistry()
        with pytest.raises(TypeError):
            registry.register({"name": "not_a_descriptor"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# schemas() — Ollama function-calling format
# ---------------------------------------------------------------------------


class TestSchemasOllamaFormat:
    """Verify that ``schemas()`` emits the Ollama function-calling envelope.

    Reference (Ollama 0.4+ tool calling, OpenAI-compatible)::

        {
          "type": "function",
          "function": {
            "name": "...",
            "description": "...",
            "parameters": { /* JSON Schema */ }
          }
        }
    """

    def test_schemas_empty_when_no_tools_registered(self):
        registry = ToolRegistry()
        assert registry.schemas() == []

    def test_schemas_envelope_shape_for_single_tool(self):
        registry = ToolRegistry()
        params = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        }
        registry.register(
            _server_descriptor(
                name="calculate_tdee",
                description="Tính TDEE từ profile.",
                parameters_schema=params,
            )
        )

        schemas = registry.schemas()

        assert isinstance(schemas, list)
        assert len(schemas) == 1
        entry = schemas[0]

        # Envelope cấp ngoài.
        assert set(entry.keys()) == {"type", "function"}
        assert entry["type"] == "function"

        # Envelope cấp `function`.
        fn_block = entry["function"]
        assert isinstance(fn_block, dict)
        assert set(fn_block.keys()) == {"name", "description", "parameters"}
        assert fn_block["name"] == "calculate_tdee"
        assert fn_block["description"] == "Tính TDEE từ profile."
        assert fn_block["parameters"] == params

    def test_schemas_preserves_parameters_schema_object(self):
        """`parameters` phải pass-through nguyên JSON schema, không biến đổi."""
        registry = ToolRegistry()
        complex_schema = {
            "type": "object",
            "properties": {
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                },
                "target_kcal": {"type": "number", "exclusiveMinimum": 0},
                "dietary_restrictions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["meal_type", "target_kcal"],
            "additionalProperties": False,
        }
        registry.register(
            _server_descriptor(
                name="suggest_dish",
                description="Gợi ý món theo macro.",
                parameters_schema=complex_schema,
            )
        )

        schemas = registry.schemas()
        assert schemas[0]["function"]["parameters"] == complex_schema

    def test_schemas_emits_one_entry_per_registered_tool(self):
        registry = ToolRegistry()
        registry.register(_server_descriptor(name="calculate_tdee"))
        registry.register(_server_descriptor(name="suggest_dish"))
        registry.register(_client_descriptor(name="log_meal"))

        schemas = registry.schemas()

        assert len(schemas) == 3
        names = [entry["function"]["name"] for entry in schemas]
        assert names == ["calculate_tdee", "suggest_dish", "log_meal"]
        for entry in schemas:
            assert entry["type"] == "function"
            assert set(entry["function"].keys()) == {
                "name",
                "description",
                "parameters",
            }

    def test_schemas_does_not_leak_internal_fields(self):
        """Ollama envelope KHÔNG được chứa `side`, `idempotent`, `timeout_ms`, `fn`.

        Các field này là metadata nội bộ của dispatcher; nếu lọt vào prompt
        gửi cho LLM thì có thể làm rối format hoặc vi phạm schema strict-mode.
        """
        registry = ToolRegistry()
        registry.register(
            _server_descriptor(
                name="calculate_tdee",
                idempotent=True,
                timeout_ms=8000,
            )
        )
        registry.register(_client_descriptor(name="log_meal", idempotent=False))

        for entry in registry.schemas():
            assert "side" not in entry
            assert "idempotent" not in entry
            assert "timeout_ms" not in entry
            assert "fn" not in entry

            fn_block = entry["function"]
            assert "side" not in fn_block
            assert "idempotent" not in fn_block
            assert "timeout_ms" not in fn_block
            assert "fn" not in fn_block
