"""Actual token accounting when a model tokenizer is locally available."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Callable, Iterable


@dataclass(frozen=True, slots=True)
class TokenMeasurements:
    tokenizer_method: str
    exact_tokenizer: bool
    production_prompt_tokens: int
    production_context_tokens: int
    production_tool_schema_tokens: int
    shadow_context_tokens: int
    shadow_tool_schema_tokens: int

    @property
    def production_total_tokens(self) -> int:
        return self.production_prompt_tokens + self.production_context_tokens + self.production_tool_schema_tokens

    @property
    def shadow_total_tokens(self) -> int:
        return self.shadow_context_tokens + self.shadow_tool_schema_tokens

    def to_dict(self) -> dict[str, object]:
        return {
            "tokenizer_method": self.tokenizer_method,
            "exact_tokenizer": self.exact_tokenizer,
            "production_prompt_tokens": self.production_prompt_tokens,
            "production_context_tokens": self.production_context_tokens,
            "production_tool_schema_tokens": self.production_tool_schema_tokens,
            "production_total_tokens": self.production_total_tokens,
            "shadow_context_tokens": self.shadow_context_tokens,
            "shadow_tool_schema_tokens": self.shadow_tool_schema_tokens,
            "shadow_total_tokens": self.shadow_total_tokens,
        }


class TokenCounter:
    def __init__(self, encode: Callable[[str], Iterable[Any]] | None = None, *, method: str = "UTF8_BYTES_CEIL4") -> None:
        self._encode = encode
        self.method = method if encode is not None else "UTF8_BYTES_CEIL4_APPROXIMATION"
        self.exact = encode is not None

    @classmethod
    def from_llm(cls, llm: Any, model: str) -> "TokenCounter":
        tokenizer = getattr(llm, "tokenizer", None)
        encode = getattr(tokenizer, "encode", None)
        if callable(encode):
            return cls(encode, method=f"LLM_TOKENIZER:{model}")
        # tiktoken is optional and is not installed by this feature. Use it
        # only when already present and when it recognizes the configured model.
        try:  # pragma: no cover - environment-dependent optional path
            import tiktoken

            encoding = tiktoken.encoding_for_model(model)
            return cls(encoding.encode, method=f"TIKTOKEN:{encoding.name}")
        except Exception:
            return cls()

    def count(self, value: Any) -> int:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if self._encode is not None:
            return len(list(self._encode(text)))
        return math.ceil(len(text.encode("utf-8")) / 4)


def measure_turn_tokens(
    *, messages: list[dict[str, Any]], production_tool_schemas: list[dict[str, Any]] | None,
    shadow_bundle: dict[str, Any], shadow_tool_names: tuple[str, ...],
    all_tool_schemas: list[dict[str, Any]], counter: TokenCounter,
) -> TokenMeasurements:
    system_messages = [item for item in messages if item.get("role") == "system"]
    context_messages = [item for item in messages if item.get("role") != "system"]
    permitted = set(shadow_tool_names)
    shadow_schemas = [
        item for item in all_tool_schemas
        if isinstance(item.get("function"), dict) and item["function"].get("name") in permitted
    ]
    return TokenMeasurements(
        tokenizer_method=counter.method, exact_tokenizer=counter.exact,
        production_prompt_tokens=counter.count(system_messages),
        production_context_tokens=counter.count(context_messages),
        production_tool_schema_tokens=counter.count(production_tool_schemas or []),
        shadow_context_tokens=counter.count(shadow_bundle),
        shadow_tool_schema_tokens=counter.count(shadow_schemas),
    )


__all__ = ["TokenCounter", "TokenMeasurements", "measure_turn_tokens"]
