"""Explicit context assembly for isolated research conditions."""

from __future__ import annotations

import json
from collections.abc import Sequence

from services.agent.tool_registry import ToolRegistry
from services.experiment.config import (
    NUTRITION_ABLATION_PROMPT_VERSION,
    ExperimentConfig,
)
from services.experiment.errors import ExperimentError
from services.experiment.models import (
    ExperimentProfile,
    FrozenRagChunk,
    ResearchContext,
)


_BASE_PROMPTS: dict[str, str] = {
    "research-v1": """RESEARCH NUTRITION ASSISTANT

You provide concise, general nutrition information for a controlled research study.
Use only the information explicitly included in this request. Do not invent user data,
food composition values, citations, or completed actions. Explain uncertainty clearly.
Do not diagnose disease or prescribe medication. If a request indicates an emergency,
advise the person to seek immediate professional help.

REFERENCE TIME (FROZEN): {frozen_time}
""".strip(),
    NUTRITION_ABLATION_PROMPT_VERSION: """TRỢ LÝ NGHIÊN CỨU DINH DƯỠNG

Bạn cung cấp thông tin chung về dinh dưỡng và vận động cho người trưởng thành
khỏe mạnh trong một nghiên cứu có kiểm soát. Luôn trả lời bằng tiếng Việt, rõ
ràng và ngắn gọn. Không chẩn đoán bệnh, kê thuốc hoặc thay thế chuyên gia y tế.
Nếu yêu cầu có dấu hiệu cấp cứu hoặc vượt ngoài phạm vi nghiên cứu, hãy nói rõ
giới hạn và khuyến nghị tìm hỗ trợ chuyên môn phù hợp.

Chỉ sử dụng hồ sơ, bằng chứng RAG và công cụ khi các khối tương ứng thực sự có
trong request. Không suy đoán dữ liệu hồ sơ còn thiếu, không tạo nguồn hoặc số
liệu giả, và không tuyên bố đã thực hiện hành động ngoài đời thực. Khi có khối
FROZEN RAG CONTEXT, các khẳng định dựa trên khối đó phải trích chunk_id dưới
dạng [chunk_id]. Khi bằng chứng không đủ, hãy nói rõ là chưa đủ thông tin.

REFERENCE TIME (FROZEN): {frozen_time}
""".strip(),
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def assemble_research_context(
    *,
    config: ExperimentConfig,
    user_query: str,
    profile: ExperimentProfile,
    rag_chunks: Sequence[FrozenRagChunk] | None,
    tool_registry: ToolRegistry,
) -> ResearchContext:
    """Build exactly the context authorized by the selected research arm.

    The initial message list always has two entries: one system message and the
    current user query. No production history or memory object is accepted by
    this function's interface.
    """

    query = user_query.strip()
    if not query:
        raise ExperimentError("EXPERIMENT_INVALID_QUERY")

    template = _BASE_PROMPTS.get(config.prompt_version)
    if template is None:
        raise ExperimentError(
            "EXPERIMENT_UNKNOWN_PROMPT_VERSION", config.prompt_version
        )

    sections = [
        template.format(frozen_time=config.frozen_time.isoformat())
    ]

    if config.profile_enabled:
        sections.extend(
            [
                "EXPERIMENT PROFILE",
                _canonical_json(profile.model_dump(mode="json")),
            ]
        )

    normalized_chunks = tuple(rag_chunks or ())
    if config.rag_enabled:
        if not normalized_chunks:
            raise ExperimentError("EXPERIMENT_RAG_NO_RESULTS")
        sections.extend(
            [
                "FROZEN RAG CONTEXT",
                _canonical_json(
                    [chunk.model_dump(mode="json") for chunk in normalized_chunks]
                ),
            ]
        )
    elif normalized_chunks:
        raise ExperimentError("EXPERIMENT_UNAUTHORIZED_RAG_CONTEXT")

    schemas = tuple(tool_registry.schemas())
    if config.nutrition_tools_enabled:
        names = tuple(schema["function"]["name"] for schema in schemas)
        if names != ("calculate_tdee",):
            raise ExperimentError(
                "EXPERIMENT_INVALID_TOOL_ALLOWLIST", ",".join(names)
            )
        sections.extend(
            [
                "DETERMINISTIC NUTRITION TOOL SCHEMAS",
                _canonical_json(list(schemas)),
            ]
        )
    elif schemas:
        raise ExperimentError("EXPERIMENT_UNAUTHORIZED_TOOLS")

    system_prompt = "\n\n".join(sections)
    messages = (
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    )
    return ResearchContext(
        rendered_system_prompt=system_prompt,
        messages=messages,
        tool_schemas=schemas,
        rag_chunks=normalized_chunks,
    )


__all__ = ["assemble_research_context"]
