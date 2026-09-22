from __future__ import annotations

from services.agent.cost_governor import limits_for_turn
from services.agent.system_prompt import buildSystemPrompt
from services.agent.turn_router import classify_turn


def _schemas(*names: str):
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"Tool {name} with a deliberately ordinary description",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in names
    ]


def test_optimized_governor_has_hard_call_output_and_history_caps() -> None:
    simple = limits_for_turn(classify_turn("100g ức gà bao nhiêu protein?"))
    complex_turn = limits_for_turn(
        classify_turn("Phân tích tuần qua và lập kế hoạch giảm cân cho tôi")
    )

    assert simple.prompt_mode == "compact"
    assert simple.max_llm_calls == 2
    assert simple.max_output_tokens == 512
    assert simple.history_turn_limit == 12
    assert complex_turn.max_llm_calls == 3
    assert complex_turn.max_output_tokens == 1200
    assert complex_turn.history_turn_limit == 24


def test_compact_prompt_removes_most_static_prompt_tokens() -> None:
    tools = _schemas("search_food_nutrition", "search_dish_catalog")
    full = buildSystemPrompt("", [], [], tool_catalog=tools, mode="full")
    compact = buildSystemPrompt("", [], [], tool_catalog=tools, mode="compact")

    assert "search_food_nutrition" in compact
    assert "REFERENCE_ONLY" in compact
    assert len(compact) < len(full) * 0.25


def test_evidence_contract_is_present_for_full_and_rag_compact_prompts() -> None:
    tools = _schemas("query_rag")
    compact = buildSystemPrompt("", [], [], tool_catalog=tools, mode="compact")
    full = buildSystemPrompt("", [], [], tool_catalog=tools, mode="full")

    for prompt in (compact, full):
        assert "không tự điền phần còn thiếu bằng kiến thức nhớ sẵn" in prompt
        assert "gắn đúng với nội dung mà chúng hỗ trợ" in prompt


def test_estimated_input_tokens_includes_tool_schemas() -> None:
    limits = limits_for_turn(classify_turn("100g ức gà bao nhiêu protein?"))
    messages = [{"role": "user", "content": "hello"}]

    without_tools = limits.estimated_input_tokens(messages, None)
    with_tools = limits.estimated_input_tokens(messages, _schemas("lookup"))

    assert with_tools > without_tools
