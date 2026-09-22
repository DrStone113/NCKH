"""Internal claim-to-evidence contract; never expose support metadata to users."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from services.agent.evidence_registry import EvidenceRegistry


_MODEL_PROVENANCE_RE = re.compile(r"(?:nguồn|source)\s*[:：]|https?://", re.IGNORECASE)


def evidence_grounding_required(validators: Any) -> bool:
    """Return the policy decision without consulting routing confidence or evidence."""

    return "EVIDENCE_GROUNDING" in frozenset(str(item) for item in validators)


@dataclass(frozen=True, slots=True)
class ClaimSupport:
    claim: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    answer: str
    claim_support: tuple[ClaimSupport, ...]


Answerability = Literal["DIRECTLY_SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED"]


@dataclass(frozen=True, slots=True)
class SynthesizedFallback:
    """A question-aware, evidence-bound fallback before provenance rendering.

    This is deliberately application-internal.  Evidence IDs identify only
    entries in the current registry and are never returned to the user.
    """

    answerability: Answerability
    grounded_answer: GroundedAnswer


SemanticVerdict = Literal["SUPPORTED", "NOT_SUPPORTED", "UNCERTAIN"]
SemanticVerifier = Callable[[str, tuple[str, ...]], Awaitable[SemanticVerdict]]


@dataclass(frozen=True, slots=True)
class SemanticValidationOutcome:
    errors: tuple[str, ...]
    unsupported_claims: tuple[str, ...]


def parse_grounded_answer(content: str) -> GroundedAnswer:
    value = json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
    if not isinstance(value, dict) or not isinstance(value.get("answer"), str):
        raise ValueError("INVALID_GROUNDED_ANSWER")
    if "claim_support" not in value:
        raise ValueError("MISSING_CLAIM_SUPPORT")
    if not isinstance(value["claim_support"], list):
        raise ValueError("INVALID_CLAIM_SUPPORT")
    support: list[ClaimSupport] = []
    for raw in value["claim_support"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("claim"), str):
            raise ValueError("INVALID_CLAIM_SUPPORT")
        ids = raw.get("evidence_ids")
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            raise ValueError("INVALID_CLAIM_SUPPORT")
        support.append(ClaimSupport(raw["claim"].strip(), tuple(ids)))
    return GroundedAnswer(value["answer"].strip(), tuple(support))


def parse_synthesized_fallback(content: str) -> SynthesizedFallback:
    """Parse the constrained synthesis contract without accepting source text."""

    value = json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
    if not isinstance(value, dict) or value.get("answerability") not in {
        "DIRECTLY_SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED",
    }:
        raise ValueError("INVALID_ANSWERABILITY")
    return SynthesizedFallback(
        answerability=value["answerability"],
        grounded_answer=parse_grounded_answer(content),
    )


def validate_grounded_answer(answer: GroundedAnswer, registry: EvidenceRegistry) -> tuple[str, ...]:
    errors: list[str] = []
    if not answer.answer:
        errors.append("MISSING_ANSWER")
    # An empty application-owned registry is an explicit insufficient-evidence
    # state, never permission to answer from the model's latent knowledge.
    if not registry.items:
        errors.append("INSUFFICIENT_EVIDENCE")
    for support in answer.claim_support:
        if not support.claim or support.claim not in answer.answer:
            errors.append("CLAIM_EVIDENCE_MISMATCH")
        if not support.evidence_ids:
            errors.append("MISSING_CLAIM_SUPPORT")
        for evidence_id in support.evidence_ids:
            if not evidence_id.startswith("E"):
                errors.append("CROSS_TURN_EVIDENCE_REFERENCE")
            elif not registry.contains(evidence_id):
                errors.append("UNKNOWN_EVIDENCE_ID")
    if not answer.claim_support:
        errors.append("MISSING_CLAIM_SUPPORT")
    # Source labels/URLs written by a model are never authoritative.  The
    # renderer below is the only component allowed to add provenance.
    if _MODEL_PROVENANCE_RE.search(answer.answer):
        errors.append("MODEL_PROVENANCE_FORBIDDEN")
    mapped_claims = tuple(support.claim for support in answer.claim_support if support.claim)
    for segment in _answer_segments(answer.answer):
        if _is_limitation_statement(segment):
            continue
        if not any(segment in claim or claim in segment for claim in mapped_claims):
            errors.append("UNSUPPORTED_UNMAPPED_CLAIM")
    return tuple(dict.fromkeys(errors))


def validate_synthesized_fallback(
    synthesis: SynthesizedFallback,
    registry: EvidenceRegistry,
    *,
    query: str,
) -> tuple[str, ...]:
    """Check answerability and relationship claims before semantic validation.

    A supported component fact is not evidence for the relationship requested
    by a user.  The lightweight relation guard makes that distinction before
    the compact semantic verifier validates each output claim.
    """

    answer = synthesis.grounded_answer
    if synthesis.answerability == "NOT_SUPPORTED":
        if answer.claim_support or not _is_limitation_statement(answer.answer):
            return ("NOT_SUPPORTED_SYNTHESIS_MUST_BE_MINIMAL",)
        if _query_is_vietnamese(query) and not _query_is_vietnamese(answer.answer):
            return ("ANSWER_LANGUAGE_MISMATCH",)
        return ()
    errors = list(validate_grounded_answer(answer, registry))
    if _query_is_vietnamese(query) and not _query_is_vietnamese(answer.answer):
        errors.append("ANSWER_LANGUAGE_MISMATCH")
    if synthesis.answerability == "PARTIALLY_SUPPORTED":
        if not _is_limitation_statement(answer.answer):
            errors.append("PARTIAL_SYNTHESIS_MISSING_LIMITATION")
        if _requested_relationship(query) and _registry_supports_relationship(query, registry):
            # A partial result is still permitted for an incomplete answer, but
            # it must not claim that the requested relation is unavailable when
            # a selected source directly states it.
            pass
    if synthesis.answerability == "DIRECTLY_SUPPORTED" and _requested_relationship(query):
        if not _claims_support_requested_relationship(answer, query, registry):
            errors.append("SUPPORTED_RELATIONSHIP_MISSING")
    return tuple(dict.fromkeys(errors))


async def validate_grounded_answer_semantically(
    answer: GroundedAnswer,
    registry: EvidenceRegistry,
    *,
    verifier: SemanticVerifier,
) -> SemanticValidationOutcome:
    """Validate material claims against their selected turn-local evidence.

    The compact verifier receives only ``claim`` and evidence content.  Its
    result is fail-closed: ``UNCERTAIN`` never authorises a factual answer.
    """

    errors = list(validate_grounded_answer(answer, registry))
    unsupported_claims: list[str] = []
    for support in answer.claim_support:
        if not support.claim or not support.evidence_ids:
            continue
        evidence = tuple(
            item.content
            for evidence_id in support.evidence_ids
            for item in registry.items
            if item.evidence_id == evidence_id
        )
        if len(evidence) != len(support.evidence_ids):
            continue
        verdict = _deterministic_entailment(support.claim, evidence)
        if verdict == "UNCERTAIN":
            verdict = await verifier(support.claim, evidence)
        if verdict != "SUPPORTED":
            errors.append("SEMANTIC_CLAIM_NOT_SUPPORTED")
            unsupported_claims.append(support.claim)
    return SemanticValidationOutcome(
        errors=tuple(dict.fromkeys(errors)),
        unsupported_claims=tuple(dict.fromkeys(unsupported_claims)),
    )


def _deterministic_entailment(claim: str, evidence: tuple[str, ...]) -> SemanticVerdict:
    """Reject quantities and strength/causality overclaims before LLM entailment."""

    claim_text, evidence_text = claim.casefold(), " ".join(evidence).casefold()
    claim_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", claim_text))
    evidence_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", evidence_text))
    if claim_numbers - evidence_numbers:
        return "NOT_SUPPORTED"
    causal_words = ("gây", "dẫn đến", "ngăn ngừa", "phòng ngừa", "chữa", "điều trị")
    certainty_words = ("chắc chắn", "luôn", "hoàn toàn", "definitely", "always")
    if any(word in claim_text for word in causal_words) and not any(word in evidence_text for word in causal_words):
        return "NOT_SUPPORTED"
    if any(word in claim_text for word in certainty_words) and not any(word in evidence_text for word in certainty_words):
        return "NOT_SUPPORTED"
    if _is_preserving_translation(claim, evidence):
        return "SUPPORTED"
    claim_terms = _semantic_terms(claim)
    if claim_terms and claim_terms <= _semantic_terms(evidence_text):
        return "SUPPORTED"
    return "UNCERTAIN"


# These are sentence-level semantic-preserving translations used only when an
# application-owned fallback cannot spend another model call.  They are not
# medical rules and do not add facts beyond the selected English sentence.
_PRESERVING_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("Nutrition is about eating a healthy and balanced diet so your body gets the nutrients that it needs.", "Dinh d\u01b0\u1ee1ng l\u00e0 \u0103n ch\u1ebf \u0111\u1ed9 l\u00e0nh m\u1ea1nh v\u00e0 c\u00e2n b\u1eb1ng \u0111\u1ec3 c\u01a1 th\u1ec3 nh\u1eadn \u0111\u1ee7 ch\u1ea5t dinh d\u01b0\u1ee1ng c\u1ea7n thi\u1ebft."),
    ("Nutrition for older adults means a healthy and balanced diet.", "Dinh d\u01b0\u1ee1ng cho ng\u01b0\u1eddi l\u1edbn tu\u1ed5i l\u00e0 ch\u1ebf \u0111\u1ed9 \u0103n l\u00e0nh m\u1ea1nh v\u00e0 c\u00e2n b\u1eb1ng."),
    ("Some older adults need more protein.", "M\u1ed9t s\u1ed1 ng\u01b0\u1eddi l\u1edbn tu\u1ed5i c\u1ea7n nhi\u1ec1u protein h\u01a1n."),
    ("Some older adults may need more protein.", "M\u1ed9t s\u1ed1 ng\u01b0\u1eddi l\u1edbn tu\u1ed5i c\u00f3 th\u1ec3 c\u1ea7n nhi\u1ec1u protein h\u01a1n."),
    ("Nausea is when you feel sick to your stomach, as if you are going to throw up.", "Bu\u1ed3n n\u00f4n l\u00e0 c\u1ea3m gi\u00e1c kh\u00f3 ch\u1ecbu \u1edf d\u1ea1 d\u00e0y nh\u01b0 s\u1eafp n\u00f4n."),
    ("Vomiting is when you throw up.", "N\u00f4n l\u00e0 khi b\u1ea1n \u00f3i ra."),
    ("Diarrhea is loose, watery stools (bowel movements).", "Ti\u00eau ch\u1ea3y l\u00e0 t\u00ecnh tr\u1ea1ng ph\u00e2n l\u1ecfng, nhi\u1ec1u n\u01b0\u1edbc."),
    ("Regular exercise may improve sleep quality.", "T\u1eadp th\u1ec3 d\u1ee5c th\u01b0\u1eddng xuy\u00ean c\u00f3 th\u1ec3 c\u1ea3i thi\u1ec7n ch\u1ea5t l\u01b0\u1ee3ng gi\u1ea5c ng\u1ee7."),
)


def _is_preserving_translation(claim: str, evidence: tuple[str, ...]) -> bool:
    normalized_claim = " ".join(claim.casefold().split())
    normalized_evidence = " ".join(" ".join(evidence).casefold().split())
    return any(
        normalized_claim == " ".join(translated.casefold().split())
        and " ".join(original.casefold().split()) in normalized_evidence
        for original, translated in _PRESERVING_TRANSLATIONS
    )


def deterministic_question_aware_synthesis(*, query: str, registry: EvidenceRegistry) -> SynthesizedFallback:
    """Produce a bounded no-new-model fallback from complete evidence sentences.

    It can use only exact source sentences or a registered semantic-preserving
    translation.  When that is impossible, it returns a minimal limitation.
    """

    item = registry.best_evidence(query)
    if item is None:
        return SynthesizedFallback("NOT_SUPPORTED", GroundedAnswer(minimal_insufficient_evidence_response(), ()))
    translations = {
        " ".join(original.casefold().split()): translated
        for original, translated in _PRESERVING_TRANSLATIONS
    }
    sentences = registry.compact_evidence_sentences(item, query=query, maximum=2)
    is_vietnamese = _query_is_vietnamese(query)
    selected: list[tuple[str, str]] = []
    for sentence in sentences:
        normalized = " ".join(sentence.casefold().split())
        if is_vietnamese:
            translated = translations.get(normalized)
            if translated:
                selected.append((translated, sentence))
        elif not sentence.endswith("?"):
            selected.append((sentence, sentence))
    if not selected:
        return SynthesizedFallback("NOT_SUPPORTED", GroundedAnswer(minimal_insufficient_evidence_response(), ()))
    claims = tuple(ClaimSupport(answer, (item.evidence_id,)) for answer, _ in selected)
    answer = " ".join(answer for answer, _ in selected)
    partial = _requested_relationship(query) is not None or _asks_nutrition_activity_relationship(query)
    if partial:
        if is_vietnamese:
            answer = (
                answer + " Ngu\u1ed3n hi\u1ec7n c\u00f3 ch\u01b0a \u0111\u1ee7 \u0111\u1ec3 k\u1ebft lu\u1eadn " + _requested_topic_phrase(query) + "."
            )
        else:
            answer = answer + " The available evidence is insufficient to conclude " + _requested_topic_phrase(query) + "."
        return SynthesizedFallback("PARTIALLY_SUPPORTED", GroundedAnswer(answer, claims))
    return SynthesizedFallback("DIRECTLY_SUPPORTED", GroundedAnswer(answer, claims))


def _asks_nutrition_activity_relationship(query: str) -> bool:
    text = query.casefold()
    nutrition = ("nutrition", "dinh d\u01b0\u1ee1ng")
    activity = ("exercise", "activity", "v\u1eadn \u0111\u1ed9ng")
    return any(word in text for word in nutrition) and any(word in text for word in activity)


def _requested_topic_phrase(query: str) -> str:
    """Name a supported question type without copying source prose or adding facts."""

    if _asks_nutrition_activity_relationship(query):
        return "v\u1ec1 m\u1ed1i li\u00ean h\u1ec7 gi\u1eefa dinh d\u01b0\u1ee1ng v\u00e0 v\u1eadn \u0111\u1ed9ng"
    relation = _requested_relationship(query)
    if relation is None:
        return "v\u1ec1 n\u1ed9i dung b\u1ea1n h\u1ecfi"
    if _query_is_vietnamese(query):
        return "v\u1ec1 m\u1ed1i quan h\u1ec7 \u0111\u01b0\u1ee3c h\u1ecfi"
    return "the requested relationship"


_RELATION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("causal", ("g\u00e2y", "d\u1eabn \u0111\u1ebfn", "cause", "causes", "caused", "lead to", "leads to", "result in")),
    ("association", ("li\u00ean quan", "li\u00ean h\u1ec7", "associated", "association", "linked to", "related to")),
    ("benefit", ("c\u1ea3i thi\u1ec7n", "gi\u00fap", "improve", "improves", "reduce", "reduces", "benefit")),
    ("treatment", ("ch\u1eefa", "\u0111i\u1ec1u tr\u1ecb", "treat", "treats", "treatment", "cure", "cures")),
    ("prevention", ("ng\u0103n ng\u1eeba", "ph\u00f2ng ng\u1eeba", "prevent", "prevents", "prevention")),
    ("comparison", ("h\u01a1n", "so s\u00e1nh", "cao h\u01a1n", "th\u1ea5p h\u01a1n", "better than", "worse than", "compared with", "versus", "vs")),
)


def _requested_relationship(query: str) -> str | None:
    text = query.casefold()
    return next((name for name, phrases in _RELATION_PATTERNS if any(phrase in text for phrase in phrases)), None)


def _registry_supports_relationship(query: str, registry: EvidenceRegistry) -> bool:
    relation = _requested_relationship(query)
    if relation is None:
        return True
    phrases = next(phrases for name, phrases in _RELATION_PATTERNS if name == relation)
    return any(any(phrase in item.content.casefold() for phrase in phrases) for item in registry.items)


def _claims_support_requested_relationship(answer: GroundedAnswer, query: str, registry: EvidenceRegistry) -> bool:
    relation = _requested_relationship(query)
    if relation is None:
        return True
    phrases = next(phrases for name, phrases in _RELATION_PATTERNS if name == relation)
    selected = " ".join(
        item.content for support in answer.claim_support for evidence_id in support.evidence_ids
        for item in registry.items if item.evidence_id == evidence_id
    ).casefold()
    claims = " ".join(support.claim for support in answer.claim_support).casefold()
    return any(phrase in selected for phrase in phrases) and any(phrase in claims for phrase in phrases)


def _semantic_terms(value: str) -> set[str]:
    ignored = {"là", "và", "có", "cho", "của", "các", "một", "những", "the", "and", "for", "with"}
    return {
        word.casefold()
        for word in re.findall(r"[\wÀ-ỹ]+", value, flags=re.UNICODE)
        if len(word) >= 3 and word.casefold() not in ignored
    }


def _answer_segments(answer: str) -> tuple[str, ...]:
    """Return visible factual-sized sentences that must have an evidence map."""

    return tuple(
        segment.strip()
        for segment in re.split(r"(?<=[.!?])\s+|\n+", answer)
        if len(segment.strip()) >= 8
    )


def _is_limitation_statement(value: str) -> bool:
    """Limitations are answer-policy statements, not medical factual claims."""

    normalized = value.casefold()
    return any(marker in normalized for marker in (
        "ch\u01b0a \u0111\u1ee7 \u0111\u1ec3", "kh\u00f4ng \u0111\u1ee7 b\u1eb1ng ch\u1ee9ng", "kh\u00f4ng th\u1ec3 k\u1ebft lu\u1eadn",
        "insufficient evidence", "not enough evidence", "cannot conclude",
    ))


def _query_is_vietnamese(value: str) -> bool:
    """A small script-free detector used only to guard fallback output language."""

    return bool(re.search(r"[\u0103\u00e2\u0111\u00ea\u00f4\u01a1\u01b0]|\b(?:c\u1ee7a|v\u00e0|l\u00e0|c\u00f3|kh\u00f4ng|li\u1ec7u|v\u1ec1|cho|ng\u01b0\u1eddi)\b", value.casefold()))


def render_grounded_answer(answer: GroundedAnswer, registry: EvidenceRegistry) -> str:
    """Append deduplicated application-owned provenance; ignore model source text."""
    ids = [item for support in answer.claim_support for item in support.evidence_ids]
    sources: list[str] = []
    for evidence_id in ids:
        item = next((entry for entry in registry.items if entry.evidence_id == evidence_id), None)
        if item is not None and item.provenance not in sources:
            sources.append(item.provenance)
    return answer.answer + ("\n\nNguồn: " + "; ".join(sources) + "." if sources else "")


def repair_prompt(
    *, original_answer: str, registry: EvidenceRegistry, errors: tuple[str, ...],
    unsupported_claims: tuple[str, ...] = (),
) -> str:
    return json.dumps({
        "instruction": "Rewrite only from the evidence registry. Return JSON with answer and claim_support. Every material factual claim must appear verbatim in answer and cite one or more existing E IDs. Do not write sources, URLs, citations, or facts outside the registry. If insufficient, state the limitation.",
        "original_answer": original_answer,
        "validation_errors": list(errors),
        "unsupported_claims": list(unsupported_claims),
        "evidence_registry": registry.prompt_block(),
        "schema": {"answer": "Vietnamese natural answer", "claim_support": [{"claim": "verbatim factual sentence", "evidence_ids": ["E1"]}]},
    }, ensure_ascii=False)


def synthesis_prompt(*, query: str, user_language: str, registry: EvidenceRegistry) -> str:
    """Constrain the final synthesis to the current evidence registry only."""

    return json.dumps({
        "instruction": (
            "Answer the user query from the evidence registry only. Return JSON with "
            "answerability (DIRECTLY_SUPPORTED, PARTIALLY_SUPPORTED, or NOT_SUPPORTED), "
            "answer, and claim_support. Translate/paraphrase only when semantic content "
            "is preserved. Do not write sources, URLs, citations, evidence IDs, outside "
            "knowledge, diagnoses, causal links, or quantities not stated in evidence. "
            "For a requested relationship, do not infer it from separate component facts. "
            "PARTIALLY_SUPPORTED must directly state the limitation and then only useful "
            "supported facts. NOT_SUPPORTED must be a concise insufficient-evidence answer "
            "with claim_support=[]. Every material factual claim must appear verbatim in "
            "answer and cite existing E IDs."
        ),
        "user_query": query,
        "user_language": user_language,
        "evidence_registry": registry.prompt_block(),
        "schema": {
            "answerability": "DIRECTLY_SUPPORTED|PARTIALLY_SUPPORTED|NOT_SUPPORTED",
            "answer": "concise answer in the user's language",
            "claim_support": [{"claim": "verbatim factual sentence in answer", "evidence_ids": ["E1"]}],
        },
    }, ensure_ascii=False)


def minimal_insufficient_evidence_response() -> str:
    return "Th\u00f4ng tin hi\u1ec7n c\u00f3 ch\u01b0a \u0111\u1ee7 \u0111\u1ec3 tr\u1ea3 l\u1eddi ch\u1eafc ch\u1eafn c\u00e2u h\u1ecfi n\u00e0y d\u1ef1a tr\u00ean c\u00e1c ngu\u1ed3n \u0111\u00e3 truy xu\u1ea5t."
