from __future__ import annotations

import asyncio
import pytest

from services.agent.answer_validators import validate_answer
from services.agent.evidence_registry import EvidenceRegistry
from services.agent.grounded_answer import (
    GroundedAnswer,
    ClaimSupport,
    SynthesizedFallback,
    deterministic_question_aware_synthesis,
    evidence_grounding_required,
    minimal_insufficient_evidence_response,
    parse_grounded_answer,
    parse_synthesized_fallback,
    render_grounded_answer,
    validate_grounded_answer,
    validate_grounded_answer_semantically,
    validate_synthesized_fallback,
)
from services.agent.llm_client import ToolCall
from services.agent.tool_dispatcher import ToolResult


def _validate(result: ToolResult):
    return validate_answer(
        "Một khẳng định sức khỏe có vẻ chắc chắn.",
        validators=("EVIDENCE_GROUNDING",),
        tool_results=((ToolCall("rag-1", "query_rag", {}), result),),
    )


def test_evidence_grounding_rejects_successful_but_empty_retrieval() -> None:
    outcome = _validate(ToolResult(ok=True, data=[]))

    assert not outcome.passed
    assert outcome.failure_codes == ("EVIDENCE_MISSING",)
    assert outcome.correction


def test_evidence_grounding_accepts_context_chunks_forwarded_to_generation() -> None:
    outcome = _validate(ToolResult(ok=True, data={"chunks": [{"content": "Nguồn đã truy xuất"}]}))

    assert outcome.passed


def test_evidence_registry_uses_application_owned_ids_and_source_metadata() -> None:
    registry = EvidenceRegistry.from_tool_results((
        (ToolCall("rag-1", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
            "title": "Nguồn", "content": "Nội dung đã xác minh",
            "metadata": {"source": {"source_name": "Bộ Y tế"}},
        }]})),
    ))

    assert registry.items[0].evidence_id == "E1"
    assert registry.items[0].provenance == "Bộ Y tế"
    assert registry.contains("E1")
    assert not registry.contains("E999")


def _registry() -> EvidenceRegistry:
    return EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
        "title": "Nguồn", "content": "Sự thật đã xác minh.", "metadata": {"source": {"source_name": "Nguồn chuẩn"}},
    }]})),))


def test_grounding_policy_is_independent_of_routing_confidence() -> None:
    assert evidence_grounding_required(("EVIDENCE_GROUNDING",))
    assert not evidence_grounding_required(())


def test_valid_evidence_and_supported_claim_is_accepted_directly() -> None:
    answer = GroundedAnswer("Sự thật đã xác minh.", (ClaimSupport("Sự thật đã xác minh.", ("E1",)),))

    assert validate_grounded_answer(answer, _registry()) == ()


def test_unsupported_extra_fact_is_rejected_before_repair_or_fallback() -> None:
    answer = GroundedAnswer(
        "Sự thật đã xác minh. Một khẳng định khác không có bằng chứng.",
        (ClaimSupport("Sự thật đã xác minh.", ("E1",)),),
    )

    assert "UNSUPPORTED_UNMAPPED_CLAIM" in validate_grounded_answer(answer, _registry())


def test_empty_registry_enters_validation_and_fails_closed() -> None:
    answer = GroundedAnswer("Sự thật.", (ClaimSupport("Sự thật.", ("E1",)),))

    assert "INSUFFICIENT_EVIDENCE" in validate_grounded_answer(answer, EvidenceRegistry.from_tool_results(()))


def test_missing_claim_support_is_a_parse_failure() -> None:
    with pytest.raises(ValueError, match="MISSING_CLAIM_SUPPORT"):
        parse_grounded_answer('{"answer":"Sự thật."}')


def test_malformed_claim_support_is_a_parse_failure() -> None:
    with pytest.raises(ValueError, match="INVALID_CLAIM_SUPPORT"):
        parse_grounded_answer('{"answer":"Sự thật.","claim_support":{}}')


def test_claim_support_rejects_unknown_and_cross_turn_evidence_ids() -> None:
    registry = EvidenceRegistry.from_tool_results(())
    answer = GroundedAnswer("Sự thật.", (ClaimSupport("Sự thật.", ("E999", "OTHER-1")),))

    assert set(validate_grounded_answer(answer, registry)) == {
        "INSUFFICIENT_EVIDENCE", "UNKNOWN_EVIDENCE_ID", "CROSS_TURN_EVIDENCE_REFERENCE",
    }


def test_model_generated_source_text_is_not_trusted_as_provenance() -> None:
    answer = GroundedAnswer(
        "Sự thật đã xác minh. Nguồn: do mô hình tự nêu.",
        (ClaimSupport("Sự thật đã xác minh.", ("E1",)),),
    )

    assert "MODEL_PROVENANCE_FORBIDDEN" in validate_grounded_answer(answer, _registry())


def test_provenance_is_rendered_only_from_registry_metadata() -> None:
    registry = EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
        "title": "Nguồn", "content": "Một sự thật.", "metadata": {"source": {"source_name": "Nguồn chuẩn"}},
    }]})),))
    answer = GroundedAnswer("Một sự thật.", (ClaimSupport("Một sự thật.", ("E1",)),))

    assert render_grounded_answer(answer, registry).endswith("Nguồn: Nguồn chuẩn.")


def test_retry_registry_keeps_prior_evidence() -> None:
    prior = ToolResult(ok=True, data={"chunks": [{"content": "Bằng chứng đầu tiên.", "metadata": {"source": {"source_name": "Nguồn 1"}}}]})
    retry = ToolResult(ok=True, data={"chunks": [{"content": "Bằng chứng lần thử lại.", "metadata": {"source": {"source_name": "Nguồn 2"}}}]})
    registry = EvidenceRegistry.from_tool_results(((ToolCall("first", "query_rag", {}), prior), (ToolCall("retry", "query_rag", {}), retry)))

    assert [item.content for item in registry.items] == ["Bằng chứng đầu tiên.", "Bằng chứng lần thử lại."]


def test_empty_retry_does_not_overwrite_prior_evidence_envelope() -> None:
    prior = ToolResult(ok=True, data={"chunks": [{"content": "Bằng chứng đầu tiên.", "metadata": {"source": {"source_name": "Nguồn 1"}}}]})
    retry = ToolResult(ok=True, data={"chunks": []})
    registry = EvidenceRegistry.from_tool_results(((ToolCall("first", "query_rag", {}), prior), (ToolCall("retry", "query_rag", {}), retry)))

    assert len(registry.items) == 1
    assert registry.items[0].content == "Bằng chứng đầu tiên."


def test_every_grounding_required_candidate_calls_the_same_validator() -> None:
    candidates = (
        GroundedAnswer("Sự thật đã xác minh.", (ClaimSupport("Sự thật đã xác minh.", ("E1",)),)),
        GroundedAnswer("Một điều khác.", (ClaimSupport("Một điều khác.", ("E999",)),)),
    )

    outcomes = [validate_grounded_answer(candidate, _registry()) for candidate in candidates if evidence_grounding_required(("EVIDENCE_GROUNDING",))]
    assert len(outcomes) == 2
    assert outcomes[0] == ()
    assert outcomes[1] == ("UNKNOWN_EVIDENCE_ID",)


def test_no_silent_bypass_when_policy_requires_grounding() -> None:
    # A free-form answer cannot satisfy the structured parser and therefore
    # must be repaired or deterministically replaced by the orchestrator.
    with pytest.raises(ValueError):
        parse_grounded_answer("Câu trả lời tự do không có metadata.")


async def _verdict(value: str, _claim: str, _evidence: tuple[str, ...]) -> str:
    return value


def test_semantic_validator_accepts_supported_structured_fact() -> None:
    registry = EvidenceRegistry.from_tool_results(((ToolCall("food", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
        "content": "Sữa chua có 100 kcal mỗi khẩu phần.", "metadata": {"source": {"source_name": "Nguồn chuẩn"}},
    }]})),))
    answer = GroundedAnswer("Sữa chua có 100 kcal mỗi khẩu phần.", (ClaimSupport("Sữa chua có 100 kcal mỗi khẩu phần.", ("E1",)),))

    outcome = asyncio.run(validate_grounded_answer_semantically(answer, registry, verifier=lambda c, e: _verdict("UNCERTAIN", c, e)))
    assert outcome.errors == ()


def test_semantic_validator_accepts_rag_paraphrase_when_verifier_supports_it() -> None:
    answer = GroundedAnswer("Ăn đa dạng giúp bữa ăn có nhiều nhóm thực phẩm.", (ClaimSupport("Ăn đa dạng giúp bữa ăn có nhiều nhóm thực phẩm.", ("E1",)),))
    registry = EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
        "content": "Bữa ăn đa dạng gồm nhiều nhóm thực phẩm.", "metadata": {"source": {"source_name": "Nguồn chuẩn"}},
    }]})),))

    outcome = asyncio.run(validate_grounded_answer_semantically(answer, registry, verifier=lambda c, e: _verdict("SUPPORTED", c, e)))
    assert outcome.errors == ()


def test_semantic_validator_rejects_unsupported_quantity() -> None:
    answer = GroundedAnswer("Sữa chua có 200 kcal.", (ClaimSupport("Sữa chua có 200 kcal.", ("E1",)),))
    registry = EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{"content": "Sữa chua có 100 kcal.", "metadata": {}}]})),))

    outcome = asyncio.run(validate_grounded_answer_semantically(answer, registry, verifier=lambda c, e: _verdict("SUPPORTED", c, e)))
    assert "SEMANTIC_CLAIM_NOT_SUPPORTED" in outcome.errors


@pytest.mark.parametrize("claim", [
    "Thực phẩm này chữa bệnh.",
    "Thực phẩm này luôn an toàn.",
])
def test_semantic_validator_rejects_causal_or_certainty_overclaim(claim: str) -> None:
    answer = GroundedAnswer(claim, (ClaimSupport(claim, ("E1",)),))
    registry = EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{"content": "Thực phẩm này có thể phù hợp với một số người.", "metadata": {}}]})),))

    outcome = asyncio.run(validate_grounded_answer_semantically(answer, registry, verifier=lambda c, e: _verdict("SUPPORTED", c, e)))
    assert "SEMANTIC_CLAIM_NOT_SUPPORTED" in outcome.errors


def test_semantic_validator_rejects_model_memory_addition_and_uncertainty() -> None:
    claim = "Thực phẩm này làm tăng trí nhớ."
    answer = GroundedAnswer(claim, (ClaimSupport(claim, ("E1",)),))
    registry = EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{"content": "Thực phẩm này chứa protein.", "metadata": {}}]})),))

    outcome = asyncio.run(validate_grounded_answer_semantically(answer, registry, verifier=lambda c, e: _verdict("UNCERTAIN", c, e)))
    assert outcome.unsupported_claims == (claim,)
    assert "SEMANTIC_CLAIM_NOT_SUPPORTED" in outcome.errors


def test_repaired_supported_claim_is_accepted_semantically() -> None:
    answer = GroundedAnswer("Thực phẩm này chứa protein.", (ClaimSupport("Thực phẩm này chứa protein.", ("E1",)),))
    registry = EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{"content": "Thực phẩm này chứa protein.", "metadata": {}}]})),))

    outcome = asyncio.run(validate_grounded_answer_semantically(answer, registry, verifier=lambda c, e: _verdict("NOT_SUPPORTED", c, e)))
    assert outcome.errors == ()


def test_fallback_is_concise_query_focused_and_preserves_provenance() -> None:
    content = (
        "Nutrition for older adults means a healthy and balanced diet. "
        "Some older adults may need more protein. "
        "This unrelated background sentence must not be reproduced in the fallback."
    )
    registry = EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
        "title": "Nutrition for Older Adults", "content": content,
        "metadata": {"source": {"source_name": "U.S. National Library of Medicine"}},
    }]})),))

    fallback = registry.evidence_only_fallback(query="Nutrition for Older Adults")
    assert "Nutrition for older adults means a healthy and balanced diet." in fallback
    assert "This unrelated background" not in fallback
    assert fallback.endswith("Nguồn: U.S. National Library of Medicine.")
    assert len(fallback.split(". ")) <= 3


def test_fallback_prefers_title_match_and_omits_source_questions() -> None:
    registry = EvidenceRegistry.from_tool_results((
        (ToolCall("wrong", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
            "title": "Constipation", "content": "Health information is available. Constipation has another topic.", "metadata": {"source": {"source_name": "A"}},
        }]})),
        (ToolCall("right", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
            "title": "Diarrhea", "content": "What is diarrhea? Diarrhea is loose, watery stools.", "metadata": {"source": {"source_name": "B"}},
        }]})),
    ))

    fallback = registry.evidence_only_fallback(query="health diarrhea")
    assert "Diarrhea is loose, watery stools." in fallback
    assert "What is diarrhea?" not in fallback
    assert "Constipation" not in fallback


def _english_evidence_registry(content: str) -> EvidenceRegistry:
    return EvidenceRegistry.from_tool_results(((ToolCall("rag", "query_rag", {}), ToolResult(ok=True, data={"chunks": [{
        "title": "Sleep and exercise", "content": content,
        "metadata": {"source": {"source_name": "Evidence publisher"}},
    }]})),))


def test_synthesis_vietnamese_query_with_english_evidence_uses_vietnamese_answer() -> None:
    registry = _english_evidence_registry("Regular exercise may improve sleep quality.")
    synthesis = SynthesizedFallback(
        "DIRECTLY_SUPPORTED",
        GroundedAnswer("Tập thể dục thường xuyên có thể cải thiện chất lượng giấc ngủ.", (
            ClaimSupport("Tập thể dục thường xuyên có thể cải thiện chất lượng giấc ngủ.", ("E1",)),
        )),
    )

    assert validate_synthesized_fallback(synthesis, registry, query="Tập thể dục có cải thiện giấc ngủ không?") == ()
    outcome = asyncio.run(validate_grounded_answer_semantically(
        synthesis.grounded_answer, registry, verifier=lambda c, e: _verdict("SUPPORTED", c, e),
    ))
    assert outcome.errors == ()


def test_deterministic_synthesis_translates_supported_english_evidence_without_extracting_it() -> None:
    registry = _english_evidence_registry("Regular exercise may improve sleep quality.")

    synthesis = deterministic_question_aware_synthesis(
        query="Tập thể dục ảnh hưởng giấc ngủ thế nào?", registry=registry,
    )

    assert synthesis.answerability == "DIRECTLY_SUPPORTED"
    assert synthesis.grounded_answer.answer == "Tập thể dục thường xuyên có thể cải thiện chất lượng giấc ngủ."
    outcome = asyncio.run(validate_grounded_answer_semantically(
        synthesis.grounded_answer, registry, verifier=lambda c, e: _verdict("NOT_SUPPORTED", c, e),
    ))
    assert outcome.errors == ()


def test_synthesis_english_evidence_directly_answers_supported_relation() -> None:
    registry = _english_evidence_registry("Regular exercise improves sleep quality.")
    synthesis = SynthesizedFallback(
        "DIRECTLY_SUPPORTED",
        GroundedAnswer("Regular exercise improves sleep quality.", (
            ClaimSupport("Regular exercise improves sleep quality.", ("E1",)),
        )),
    )

    assert validate_synthesized_fallback(synthesis, registry, query="Does regular exercise improve sleep quality?") == ()


def test_synthesis_classifies_component_facts_without_requested_relation_as_partial() -> None:
    registry = _english_evidence_registry("Exercise is associated with better sleep. Magnesium is present in nuts.")
    synthesis = SynthesizedFallback(
        "PARTIALLY_SUPPORTED",
        GroundedAnswer(
            "Nguồn hiện có cho thấy tập thể dục có liên quan đến giấc ngủ tốt hơn, nhưng chưa đủ để kết luận magie gây cải thiện giấc ngủ. Tập thể dục có liên quan đến giấc ngủ tốt hơn.",
            (ClaimSupport("Tập thể dục có liên quan đến giấc ngủ tốt hơn.", ("E1",)),),
        ),
    )

    assert validate_synthesized_fallback(synthesis, registry, query="Magie có gây cải thiện giấc ngủ không?") == ()


def test_synthesis_classifies_absent_relationship_as_not_supported() -> None:
    synthesis = SynthesizedFallback(
        "NOT_SUPPORTED",
        GroundedAnswer("Thông tin hiện có chưa đủ để kết luận về mối liên hệ được hỏi.", ()),
    )

    assert validate_synthesized_fallback(
        synthesis, _english_evidence_registry("Protein is a nutrient."), query="Protein có chữa mất ngủ không?",
    ) == ()


def test_synthesis_does_not_promote_association_to_causation() -> None:
    registry = _english_evidence_registry("Exercise is associated with better sleep.")
    synthesis = SynthesizedFallback(
        "DIRECTLY_SUPPORTED",
        GroundedAnswer("Tập thể dục có liên quan đến giấc ngủ tốt hơn.", (
            ClaimSupport("Tập thể dục có liên quan đến giấc ngủ tốt hơn.", ("E1",)),
        )),
    )

    assert "SUPPORTED_RELATIONSHIP_MISSING" in validate_synthesized_fallback(
        synthesis, registry, query="Tập thể dục có gây ngủ ngon hơn không?",
    )


def test_synthesized_quantity_missing_from_evidence_is_rejected() -> None:
    registry = _english_evidence_registry("Yogurt contains 100 kcal per serving.")
    answer = GroundedAnswer("Sữa chua có 200 kcal mỗi khẩu phần.", (ClaimSupport("Sữa chua có 200 kcal mỗi khẩu phần.", ("E1",)),))

    outcome = asyncio.run(validate_grounded_answer_semantically(answer, registry, verifier=lambda c, e: _verdict("SUPPORTED", c, e)))
    assert "SEMANTIC_CLAIM_NOT_SUPPORTED" in outcome.errors


def test_translated_supported_fact_is_accepted_when_semantically_entailed() -> None:
    registry = _english_evidence_registry("Nuts contain magnesium.")
    answer = GroundedAnswer("Các loại hạt có chứa magie.", (ClaimSupport("Các loại hạt có chứa magie.", ("E1",)),))

    outcome = asyncio.run(validate_grounded_answer_semantically(answer, registry, verifier=lambda c, e: _verdict("SUPPORTED", c, e)))
    assert outcome.errors == ()


def test_synthesis_does_not_reproduce_long_english_evidence() -> None:
    registry = _english_evidence_registry(" ".join([
        "Regular exercise may improve sleep quality.",
        "This long background material is not required to answer the question.",
        "It must not be copied into the concise Vietnamese response.",
    ]))
    synthesis = SynthesizedFallback(
        "DIRECTLY_SUPPORTED",
        GroundedAnswer("Tập thể dục thường xuyên có thể cải thiện chất lượng giấc ngủ.", (
            ClaimSupport("Tập thể dục thường xuyên có thể cải thiện chất lượng giấc ngủ.", ("E1",)),
        )),
    )

    assert len(synthesis.grounded_answer.answer) < 100
    assert "long background" not in synthesis.grounded_answer.answer
    assert validate_synthesized_fallback(synthesis, registry, query="Tập thể dục ảnh hưởng giấc ngủ thế nào?") == ()


def test_partial_synthesis_stays_relevant_to_the_question() -> None:
    registry = _english_evidence_registry("Exercise is associated with better sleep.")
    synthesis = SynthesizedFallback(
        "PARTIALLY_SUPPORTED",
        GroundedAnswer(
            "Nguồn hiện có chưa đủ để kết luận tập thể dục chữa mất ngủ, nhưng cho thấy tập thể dục có liên quan đến giấc ngủ tốt hơn.",
            (ClaimSupport("tập thể dục có liên quan đến giấc ngủ tốt hơn.", ("E1",)),),
        ),
    )

    assert validate_synthesized_fallback(synthesis, registry, query="Tập thể dục có chữa mất ngủ không?") == ()


def test_synthesized_fallback_passes_the_same_semantic_entailment_validator() -> None:
    registry = _english_evidence_registry("Regular exercise improves sleep quality.")
    synthesis = parse_synthesized_fallback(
        '{"answerability":"DIRECTLY_SUPPORTED","answer":"Regular exercise improves sleep quality.","claim_support":[{"claim":"Regular exercise improves sleep quality.","evidence_ids":["E1"]}]}'
    )

    assert validate_synthesized_fallback(synthesis, registry, query="Does exercise improve sleep quality?") == ()
    outcome = asyncio.run(validate_grounded_answer_semantically(
        synthesis.grounded_answer, registry, verifier=lambda c, e: _verdict("SUPPORTED", c, e),
    ))
    assert outcome.errors == ()


def test_synthesized_provenance_remains_registry_metadata_only() -> None:
    registry = _english_evidence_registry("Regular exercise improves sleep quality.")
    answer = GroundedAnswer("Regular exercise improves sleep quality.", (ClaimSupport("Regular exercise improves sleep quality.", ("E1",)),))

    rendered = render_grounded_answer(answer, registry)
    assert rendered.endswith("Nguồn: Evidence publisher.")
    assert "E1" not in rendered


def test_invalid_synthesis_closes_to_minimal_insufficient_evidence_response() -> None:
    synthesis = SynthesizedFallback(
        "NOT_SUPPORTED",
        GroundedAnswer("Protein chữa mất ngủ.", (ClaimSupport("Protein chữa mất ngủ.", ("E1",)),)),
    )

    assert validate_synthesized_fallback(
        synthesis, _english_evidence_registry("Protein is a nutrient."), query="Protein có chữa mất ngủ không?",
    ) == ("NOT_SUPPORTED_SYNTHESIS_MUST_BE_MINIMAL",)
    assert "chưa đủ" in minimal_insufficient_evidence_response()
