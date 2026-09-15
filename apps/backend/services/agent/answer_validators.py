"""Deterministic post-generation validators for high-risk chat answers.

The checks intentionally consume typed tool outcomes, never hidden model
reasoning. A failed hard check returns a safe correction/clarification rather
than asking another model to invent missing facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from services.agent.tool_dispatcher import ToolResult


_NUMBER_RE = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)?")
_NUMERIC_CLAIM_RE = re.compile(
    r"(?<![\w])([-+]?\d+(?:[.,]\d+)?)\s*"
    r"(?:kcal|calo(?:rie)?s?|g(?:am)?|kg|%|phút|phut|minutes?|giờ|gio|hours?|ngày|ngay|days?)\b",
    re.IGNORECASE,
)
_PERSISTENCE_CLAIMS = (
    "đã lưu", "đã ghi", "đã cập nhật", "saved", "recorded", "updated",
)
_WRITE_PREFIXES = ("log_", "save_", "create_", "update_", "mark_")
_EVIDENCE_TOOLS = frozenset({"query_rag", "search_medical_knowledge"})


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    passed: bool
    failure_codes: tuple[str, ...] = ()
    correction: str | None = None


def validate_answer(
    answer: str,
    *,
    validators: Iterable[str],
    tool_results: Iterable[tuple[Any, ToolResult]],
    user_text: str = "",
) -> ValidationOutcome:
    required = frozenset(str(item) for item in validators)
    results = tuple(tool_results)
    failures: list[str] = []

    if "PERSISTENCE_CONFIRMATION" in required and _claims_persistence(answer):
        write_ok = any(
            result.ok and str(getattr(call, "name", "")).startswith(_WRITE_PREFIXES)
            for call, result in results
        )
        if not write_ok:
            failures.append("PERSISTENCE_NOT_CONFIRMED")

    if "EVIDENCE_GROUNDING" in required:
        evidence_ok = any(
            result.ok and getattr(call, "name", None) in _EVIDENCE_TOOLS
            for call, result in results
        )
        if not evidence_ok:
            failures.append("EVIDENCE_MISSING")

    if "CURRENT_STATE_FRESHNESS" in required:
        attempted_current_reads = [
            result
            for call, result in results
            if getattr(call, "name", None)
            in {"get_today_meals", "get_today_exercises", "get_lifestyle_logs", "get_active_plan", "get_active_plan_v2"}
        ]
        if not attempted_current_reads:
            failures.append("CURRENT_STATE_MISSING")
        elif not any(item.ok for item in attempted_current_reads):
            failures.append("CURRENT_STATE_UNAVAILABLE")

    if "NUMERIC_CONSISTENCY" in required:
        supported = _collect_numbers(user_text)
        for _call, result in results:
            if result.ok:
                supported.update(_collect_numbers(result.data))
        claimed = _collect_claim_numbers(answer)
        # Apply only when the turn actually supplied typed numeric authority.
        # Otherwise the evidence validator owns the missing-data decision.
        if supported and any(number not in supported for number in claimed):
            failures.append("UNSUPPORTED_NUMERIC_CLAIM")

    if "ALLERGY_CONSTRAINT" in required or "DIETARY_CONSTRAINT" in required:
        if any(_contains_explicit_constraint_violation(result.data) for _, result in results if result.ok):
            failures.append("CONSTRAINT_VIOLATION")

    if "PLAN_CONSISTENCY" in required:
        if any(_contains_plan_conflict(result) for _, result in results):
            failures.append("PLAN_CONFLICT")

    unique = tuple(dict.fromkeys(failures))
    if not unique:
        return ValidationOutcome(True)
    return ValidationOutcome(False, unique, _safe_correction(unique))


def _claims_persistence(answer: str) -> bool:
    folded = str(answer or "").casefold()
    return any(item in folded for item in _PERSISTENCE_CLAIMS)


def _collect_numbers(value: Any) -> set[Decimal]:
    numbers: set[Decimal] = set()
    if isinstance(value, bool) or value is None:
        return numbers
    if isinstance(value, (int, float, Decimal)):
        try:
            numbers.add(Decimal(str(value)).normalize())
        except InvalidOperation:
            pass
        return numbers
    if isinstance(value, dict):
        for item in value.values():
            numbers.update(_collect_numbers(item))
        return numbers
    if isinstance(value, (list, tuple, set)):
        for item in value:
            numbers.update(_collect_numbers(item))
        return numbers
    if isinstance(value, str):
        for match in _NUMBER_RE.findall(value):
            try:
                numbers.add(Decimal(match.replace(",", ".")).normalize())
            except InvalidOperation:
                continue
    return numbers


def _collect_claim_numbers(value: str) -> set[Decimal]:
    numbers: set[Decimal] = set()
    for match in _NUMERIC_CLAIM_RE.findall(str(value or "")):
        try:
            numbers.add(Decimal(match.replace(",", ".")).normalize())
        except InvalidOperation:
            continue
    return numbers


def _contains_explicit_constraint_violation(value: Any) -> bool:
    if isinstance(value, list):
        return any(_contains_explicit_constraint_violation(item) for item in value)
    if not isinstance(value, dict):
        return False
    negative_flags = (
        "allergy_safe", "dietary_safe", "restriction_safe", "eligible",
    )
    if any(value.get(key) is False for key in negative_flags):
        return True
    if value.get("constraint_violations") or value.get("allergens_detected"):
        return True
    return any(
        _contains_explicit_constraint_violation(item)
        for item in value.values()
        if isinstance(item, (dict, list))
    )


def _contains_plan_conflict(result: ToolResult) -> bool:
    if result.error in {"PLAN_REVISION_CONFLICT", "PLAN_CONTENT_HASH_MISMATCH"}:
        return True
    return isinstance(result.data, dict) and result.data.get("status") == "CONFLICT"


def _safe_correction(codes: tuple[str, ...]) -> str:
    if "PERSISTENCE_NOT_CONFIRMED" in codes:
        return "Mình chưa nhận được xác nhận lưu thành công, nên chưa thể nói dữ liệu đã được ghi. Bạn có thể thử xác nhận lại."
    if "CONSTRAINT_VIOLATION" in codes:
        return "Kết quả hiện tại chưa vượt qua kiểm tra dị ứng hoặc chế độ ăn, nên mình không thể đề xuất nó. Hãy cho mình thêm thông tin để chọn phương án an toàn hơn."
    if "EVIDENCE_MISSING" in codes:
        return "Mình chưa lấy được nguồn bằng chứng cần thiết để trả lời chắc chắn. Bạn muốn mình thử lại truy vấn nguồn hay làm rõ câu hỏi trước?"
    if "CURRENT_STATE_UNAVAILABLE" in codes or "CURRENT_STATE_MISSING" in codes:
        return "Mình chưa đọc được dữ liệu hiện tại nên chưa thể kết luận chính xác. Bạn thử lại sau hoặc cung cấp rõ dữ liệu cần kiểm tra nhé."
    if "PLAN_CONFLICT" in codes:
        return "Phiên bản kế hoạch đã thay đổi nên mình chưa áp dụng thao tác này. Hãy tải lại kế hoạch hiện tại rồi xác nhận lại."
    return "Các số liệu trong câu trả lời chưa khớp hoàn toàn với dữ liệu đã kiểm tra, nên mình chưa thể đưa ra kết luận đó."


__all__ = ["ValidationOutcome", "validate_answer"]
