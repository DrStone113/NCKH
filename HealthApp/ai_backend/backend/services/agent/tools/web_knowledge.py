"""``search_medical_knowledge`` — the agent's window onto the open internet.

The tool description is deliberately restrictive. A model handed an unqualified
"search the web" tool reaches for it constantly, which is slow, wastes the
PubMed rate budget, and produces worse answers than the local corpus for
questions the local corpus already covers. The description therefore states the
*preconditions* for calling, not just the capability.
"""

from __future__ import annotations

import logging
from typing import Any

from services.agent.tool_registry import ToolDescriptor
from services.agent.web_search import WebKnowledgeService

logger = logging.getLogger(__name__)


SEARCH_MEDICAL_KNOWLEDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 3,
            "description": (
                "Câu truy vấn. Với scope='research' hãy viết bằng TIẾNG ANH và "
                "dùng thuật ngữ khoa học (vd 'creatine supplementation muscle "
                "strength meta-analysis') vì PubMed chỉ index tiếng Anh. Với "
                "scope='web' có thể dùng tiếng Việt."
            ),
        },
        "scope": {
            "type": "string",
            "enum": ["research", "web", "all"],
            "default": "all",
            "description": (
                "research = chỉ PubMed (bài báo bình duyệt, dùng khi cần bằng "
                "chứng khoa học); web = WHO, Bộ Y tế, Viện Dinh dưỡng, bệnh "
                "viện lớn (dùng cho hướng dẫn thực hành và nội dung tiếng "
                "Việt); all = cả hai."
            ),
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 8,
            "default": 4,
            "description": "Số kết quả tối đa. 3-4 là đủ cho hầu hết câu hỏi.",
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


_DESCRIPTION = (
    "Tra cứu kiến thức y khoa/dinh dưỡng từ nguồn uy tín trên internet "
    "(PubMed, WHO, CDC, NIH, Bộ Y tế, Viện Dinh dưỡng, Mayo Clinic, Vinmec). "
    "CHỈ gọi khi: (a) phần 'Tài liệu chuyên môn liên quan' trong ngữ cảnh "
    "không có thông tin cần thiết, HOẶC (b) câu hỏi cần bằng chứng nghiên cứu, "
    "hướng dẫn điều trị, tương tác thuốc–thực phẩm, hoặc thông tin cập nhật. "
    "KHÔNG gọi cho: kiến thức dinh dưỡng phổ thông, dữ liệu cá nhân của người "
    "dùng (dùng get_* tools), tính TDEE, gợi ý món ăn hay bài tập. "
    "Kết quả trả về có 'url' và 'do_tin_cay' (1 = bình duyệt/chính phủ, "
    "2 = viện y khoa lớn, 3 = báo sức khỏe uy tín). "
    "Khi dùng thông tin từ đây, BẮT BUỘC nêu nguồn trong câu trả lời một cách "
    "tự nhiên (vd 'theo khuyến nghị của WHO' hoặc 'một phân tích tổng hợp trên "
    "PubMed cho thấy'). Nếu không có kết quả, nói thật là chưa tìm được và trả "
    "lời bằng kiến thức nền — tuyệt đối không bịa số liệu hay tên nghiên cứu."
)


def build_search_tool(
    web_service: WebKnowledgeService,
    ingest_service: Any | None = None,
):
    """Return the async callable bound to a search + ingest pipeline."""

    async def search_medical_knowledge(
        query: str,
        scope: str = "all",
        limit: int = 4,
    ) -> dict[str, Any]:
        results = await web_service.search(query, limit=limit, scope=scope)

        if not results:
            return {
                "ket_qua": [],
                "ghi_chu": (
                    "Không tìm thấy kết quả từ nguồn uy tín. Hãy trả lời bằng "
                    "kiến thức nền và nói rõ là chưa tra cứu được, đừng bịa nguồn."
                ),
            }

        # Ingestion is intentionally awaited rather than fired in the
        # background: it shares the request's DB session, which the gateway
        # closes at the end of the turn. The work is a handful of inserts plus
        # one embedding call, so the added latency is small and bounded.
        if ingest_service is not None:
            try:
                stored = await ingest_service.ingest(results)
                if stored:
                    logger.info("Learned %d new chunk(s) from this search", stored)
            except Exception as exc:  # noqa: BLE001 - never fail the tool
                logger.warning("Ingest step failed (non-fatal): %s", exc)

        return {
            "ket_qua": [r.to_dict() for r in results],
            "ghi_chu": (
                "Trích dẫn nguồn khi dùng thông tin này. Ưu tiên kết quả có "
                "do_tin_cay thấp hơn (1 là đáng tin nhất)."
            ),
        }

    return search_medical_knowledge


SEARCH_MEDICAL_KNOWLEDGE_DESCRIPTOR = ToolDescriptor(
    name="search_medical_knowledge",
    description=_DESCRIPTION,
    parameters_schema=SEARCH_MEDICAL_KNOWLEDGE_SCHEMA,
    side="server",
    fn=None,  # Bound by register_server_tools.
    idempotent=True,
    # Network + optional embedding; the default 15s is too tight for two
    # upstream providers on a cold connection.
    timeout_ms=25_000,
)


__all__ = [
    "SEARCH_MEDICAL_KNOWLEDGE_DESCRIPTOR",
    "SEARCH_MEDICAL_KNOWLEDGE_SCHEMA",
    "build_search_tool",
]
