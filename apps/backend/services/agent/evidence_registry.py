"""Turn-local, application-owned evidence identities and provenance."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from services.agent.tool_dispatcher import ToolResult


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    source_type: str
    title: str
    content: str
    provenance: str


@dataclass(frozen=True, slots=True)
class EvidenceRegistry:
    items: tuple[EvidenceItem, ...]

    @classmethod
    def from_tool_results(cls, results: Iterable[tuple[Any, ToolResult]]) -> "EvidenceRegistry":
        items: list[EvidenceItem] = []
        for call, result in results:
            if not result.ok:
                continue
            name = str(getattr(call, "name", ""))
            for chunk in _chunks(result.data):
                title = str(chunk.get("title") or name or "Dữ liệu đã xác minh")
                content = str(chunk.get("content") or chunk.get("noi_dung") or "").strip()
                if not content:
                    continue
                metadata = dict(chunk.get("metadata") or {})
                source = dict(metadata.get("source") or {})
                provenance = str(
                    source.get("source_name") or metadata.get("publisher")
                    or chunk.get("url") or chunk.get("nguon") or name
                ).strip()
                items.append(EvidenceItem(
                    evidence_id=f"E{len(items) + 1}", source_type="RAG" if name in {"query_rag", "search_medical_knowledge"} else "TOOL",
                    title=title, content=content, provenance=provenance or title,
                ))
        return cls(tuple(items))

    def contains(self, evidence_id: str) -> bool:
        return any(item.evidence_id == evidence_id for item in self.items)

    def prompt_block(self) -> str:
        if not self.items:
            return "Không có bằng chứng khả dụng."
        return "\n".join(
            f"{item.evidence_id} | {item.title} | {item.content} | source={item.provenance}"
            for item in self.items
        )

    def evidence_only_fallback(self, *, query: str = "") -> str:
        """Render a compact, query-focused deterministic evidence response."""
        if not self.items:
            return "Thông tin hiện có chưa đủ để kết luận thêm về nội dung bạn hỏi."
        item = self._best_item(query)
        excerpts = _compact_sentences(item.content, query=query, maximum=2)
        if _query_has_unsupported_domain_qualifier(query, item.title, excerpts):
            return (
                "Thông tin hiện có chưa đủ để kết luận thêm về mối liên hệ được hỏi."
                f"\n\nNguồn: {item.provenance}."
            )
        if excerpts:
            return f"Thông tin hiện có cho thấy: {' '.join(excerpts)}\n\nNguồn: {item.provenance}."
        return (
            f"Thông tin hiện có liên quan đến {item.title}, nhưng chưa đủ để kết luận thêm."
            f"\n\nNguồn: {item.provenance}."
        )

    def best_evidence(self, query: str) -> EvidenceItem | None:
        """Return the most query-relevant turn-local evidence item, if any."""

        if not self.items:
            return None
        item = self._best_item(query)
        return item if _terms(query) & _terms(item.title + " " + item.content) else None

    def compact_evidence_sentences(self, item: EvidenceItem, *, query: str, maximum: int = 2) -> tuple[str, ...]:
        """Expose bounded complete sentences for application-owned synthesis."""

        return _compact_sentences(item.content, query=query, maximum=maximum)

    def _best_item(self, query: str) -> EvidenceItem:
        query_terms = _terms(query)
        return max(
            self.items,
            key=lambda item: (
                # A title match identifies the document topic more reliably
                # than a generic word repeated in a long source body.
                10 * len(query_terms & _terms(item.title))
                + len(query_terms & _terms(item.content)),
                -len(item.content),
                item.evidence_id,
            ),
        )


def _chunks(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("chunks", value.get("results", value.get("ket_qua", [])))
    if not isinstance(value, (list, tuple)):
        return []
    output: list[dict[str, Any]] = []
    for item in value:
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            item = dump(mode="json")
        if isinstance(item, dict):
            output.append(item)
    return output


_SENTENCE_RE = re.compile(r"[^.!?]+[.!?](?:\s+|$)")
_WORD_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)
_STOPWORDS = frozenset({"và", "là", "có", "cho", "với", "của", "the", "and", "for", "what", "are", "is", "about"})


def _terms(value: str) -> set[str]:
    return {
        word.casefold() for word in _WORD_RE.findall(value)
        if len(word) >= 3 and word.casefold() not in _STOPWORDS
    }


def _compact_sentences(content: str, *, query: str, maximum: int) -> tuple[str, ...]:
    """Choose complete, non-duplicated evidence sentences; never character-cut."""

    query_terms = _terms(query)
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    compact = " ".join(content.split())
    for position, match in enumerate(_SENTENCE_RE.finditer(compact)):
        # Retain only complete sentences present in the evaluator-safe source
        # window; the application never exposes a character-truncated sentence.
        if match.end() > 512:
            break
        sentence = match.group().strip()
        normalized = " ".join(sentence.casefold().split())
        if (
            not sentence
            or len(sentence) > 360
            or normalized in seen
            or sentence.endswith("?")
            or normalized.startswith("tóm tắt")
        ):
            continue
        seen.add(normalized)
        candidates.append((len(query_terms & _terms(sentence)), -position, sentence))
    if not candidates:
        return ()
    selected = sorted(candidates, reverse=True)[:maximum]
    selected_set = {sentence for _, _, sentence in selected}
    return tuple(sentence for _, _, sentence in candidates if sentence in selected_set)


def _query_has_unsupported_domain_qualifier(
    query: str,
    title: str,
    excerpts: tuple[str, ...],
) -> bool:
    """Avoid answering a domain relationship absent from the selected source."""

    requested = _terms(query)
    present = _terms(title + " " + " ".join(excerpts))
    nutrition_or_activity = {"dinh", "dưỡng", "nutrition", "vận", "động", "exercise", "activity"}
    required = requested & nutrition_or_activity
    return bool(required and not (required & present))
