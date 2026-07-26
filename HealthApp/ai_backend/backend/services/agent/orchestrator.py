"""Agent orchestrator implementing the bounded ReAct loop.

v2 changes
----------
- **Per-turn routing** (:mod:`services.agent.turn_router`): chit-chat skips the
  tool catalog entirely and runs on the light model; complex analysis is
  escalated to the heavy model. Previously every turn paid the same price.
- **Live tool catalog in the prompt** so the model cannot invent tool names.
- **Readable tool errors.** The loop used to hand the model raw
  ``{"ok": false, "error": "INVALID_ARGS"}``, which small models answer with
  "hệ thống đang lỗi". Errors are now translated into an instruction telling
  the model what to do next, and a failed tool is retried once.
- **Memory consolidation actually runs.** ``updateRollingSummary`` existed but
  was never called from production code, so the bot never built long-term
  memory. It now fires as a background task after each completed turn.
- **Profile capture.** ``get_user_profile`` results are threaded back into the
  system prompt for the remainder of the turn.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from config import settings
from services.agent.llm_client import GarbledOutputError, LLMUnavailableError, ToolCall
from services.agent.system_prompt import buildSystemPrompt
from services.agent.tool_dispatcher import ToolResult
from services.agent.turn_router import TurnPlan, classify_turn

logger = logging.getLogger(__name__)


# Guidance handed to the model when a tool call fails, keyed by the stable
# error codes from ``ToolDispatcher``. Without this the model sees an opaque
# code and falls back on "hệ thống đang lỗi", which is exactly the behaviour
# the system prompt forbids.
_ERROR_GUIDANCE: dict[str, str] = {
    "UNKNOWN_TOOL": (
        "Tool này không tồn tại. Chỉ dùng đúng các tool trong danh sách đã cho, "
        "hoặc trả lời trực tiếp bằng kiến thức của bạn."
    ),
    "INVALID_ARGS": (
        "Tham số sai định dạng. Đọc lại schema của tool và gọi lại đúng một lần "
        "với tham số hợp lệ."
    ),
    "TIMEOUT": (
        "Tool quá hạn. Đừng gọi lại tool này. Tiếp tục tư vấn với dữ liệu đang có "
        "và nói ngắn gọn rằng phần này chưa lấy được."
    ),
    "DISCONNECTED": (
        "Ứng dụng không phản hồi. Trả lời bằng kiến thức chung, đừng nhắc tới lỗi kỹ thuật."
    ),
    "TOOL_INTERNAL_ERROR": (
        "Tool gặp sự cố. Thử một cách khác một lần, nếu vẫn hỏng thì tiếp tục tư vấn "
        "với phần dữ liệu đang có."
    ),
}

# Tool errors worth one automatic retry. A timeout or a disconnect will not fix
# itself inside the same turn, so those are not retried.
_RETRYABLE_ERRORS: frozenset[str] = frozenset({"TOOL_INTERNAL_ERROR"})


class AgentOrchestrator:
    def __init__(
        self,
        llm: Any,
        tools: Any,
        memory: Any,
        session_store: Any,
        dispatcher: Any,
        gateway: Any | None = None,
        max_steps: int | None = None,
        tool_timeout_ms: int | None = None,
        heavy_llm: Any | None = None,
    ) -> None:
        self.llm = llm
        self.heavy_llm = heavy_llm
        self.tools = tools
        self.memory = memory
        self.session_store = session_store
        self.dispatcher = dispatcher
        self.gateway = gateway
        self.max_steps = max_steps or settings.max_agent_steps
        self.tool_timeout_ms = tool_timeout_ms or settings.tool_timeout_ms
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------ main
    async def handleChatMessage(self, session_id: str, user_text: str) -> None:
        gateway = self.gateway
        performed_actions: list[dict[str, Any]] = []
        try:
            context = await self.memory.loadContext(session_id, user_text)
            plan = classify_turn(user_text, history_len=len(context.history))
            llm = self._select_llm(plan)
            tool_schemas = self.tools.schemas() if plan.offer_tools else None

            logger.info(
                "Turn routed tier=%s heavy=%s tools=%s session=%s",
                plan.tier,
                plan.use_heavy_model,
                bool(tool_schemas),
                session_id,
            )

            messages = self._build_messages(context, user_text, plan)
            await self._append_turn(session_id, "user", user_text)

            # The router proposes a per-turn budget; the constructor's
            # ``max_steps`` remains a hard ceiling so callers (and tests) keep
            # full control over the worst case.
            step_budget = max(1, min(plan.max_steps, self.max_steps))

            # Tracks how many times each tool already failed this turn, so a
            # broken tool cannot spin the loop until max_steps runs out.
            failure_counts: dict[str, int] = {}
            user_profile: Any = None

            for step in range(step_budget):
                response = await llm.chat(messages, tools=tool_schemas)
                full_response = await self._stream_final(gateway, response)

                if not response.tool_calls:
                    if full_response.strip():
                        await self._append_turn(session_id, "assistant", full_response)
                    if gateway is not None:
                        await gateway.send_done(full_response, performed_actions)
                    self._schedule_memory_update(session_id)
                    return

                if full_response.strip():
                    await self._append_turn(session_id, "assistant", full_response)

                msg: dict[str, Any] = {"role": "assistant"}
                if full_response.strip():
                    msg["content"] = full_response
                msg["tool_calls"] = [self._call_to_message(c) for c in response.tool_calls]
                messages.append(msg)

                tool_results = await self._dispatch_all(
                    session_id, response.tool_calls, failure_counts
                )

                for call, result in tool_results:
                    serialized = self._serialize_result(call, result)
                    await self._append_turn(
                        session_id, "tool", serialized,
                        tool_call_id=call.id, tool_name=call.name,
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": serialized}
                    )
                    performed_actions.append({
                        "tool": call.name,
                        "args": call.arguments,
                        "result_summary": self._summarize_result(result),
                    })
                    if call.name == "get_user_profile" and result.ok and result.data:
                        user_profile = result.data

                # Refresh the system prompt with anything we just learned about
                # the user so later steps in the same turn stop re-asking.
                if user_profile is not None:
                    messages[0]["content"] = buildSystemPrompt(
                        context.rolling_summary,
                        context.pinned_facts,
                        context.rag_chunks,
                        tool_catalog=self.tools if plan.offer_tools else None,
                        user_profile=user_profile,
                        mode=plan.prompt_mode,
                    )

                # Last permitted step: force a text answer instead of dying on
                # AGENT_LOOP_EXCEEDED, which the user reads as a crash.
                if step == step_budget - 2:
                    messages.append({
                        "role": "system",
                        "content": (
                            "Đã đủ dữ liệu. Trả lời người dùng bằng lời ngay bây giờ, "
                            "không gọi thêm tool nào nữa."
                        ),
                    })

            # Loop exhausted — make one last tool-free pass so the user still
            # gets a real answer.
            await self._final_answer_fallback(
                session_id, llm, messages, gateway, performed_actions
            )
            self._schedule_memory_update(session_id)

        except LLMUnavailableError:
            logger.warning("LLM unavailable for session=%s", session_id)
            if gateway is not None:
                await gateway.send_error(
                    "LLM_UNAVAILABLE",
                    "Mình chưa kết nối được tới máy chủ AI. Bạn thử lại sau ít phút nhé.",
                )
            await self._append_turn(session_id, "assistant", "LLM_UNAVAILABLE")
        except GarbledOutputError:
            logger.warning("Garbled LLM output for session=%s", session_id)
            if gateway is not None:
                await gateway.send_error(
                    "LLM_ERROR",
                    "Phản hồi bị lỗi ký tự. Bạn nhắn lại giúp mình nhé.",
                )
            await self._append_turn(session_id, "assistant", "LLM_ERROR")

    # ------------------------------------------------------------- internals
    def _select_llm(self, plan: TurnPlan) -> Any:
        """Return the heavy model for complex turns when one is wired in."""
        if plan.use_heavy_model and self.heavy_llm is not None:
            return self.heavy_llm
        return self.llm

    async def _dispatch_all(
        self,
        session_id: str,
        calls: list[ToolCall],
        failure_counts: dict[str, int],
    ) -> list[tuple[ToolCall, ToolResult]]:
        """Dispatch every call in parallel, retrying transient failures once."""

        async def _run(call: ToolCall) -> tuple[ToolCall, ToolResult]:
            result = await self.dispatcher.dispatch(session_id, call, self.tool_timeout_ms)
            if (
                not result.ok
                and result.error in _RETRYABLE_ERRORS
                and failure_counts.get(call.name, 0) == 0
            ):
                failure_counts[call.name] = 1
                logger.info("Retrying tool %s after %s", call.name, result.error)
                result = await self.dispatcher.dispatch(
                    session_id, call, self.tool_timeout_ms
                )
            if not result.ok:
                failure_counts[call.name] = failure_counts.get(call.name, 0) + 1
                logger.warning("Tool %s failed: %s", call.name, result.error)
            return call, result

        return list(await asyncio.gather(*[_run(call) for call in calls]))

    async def _final_answer_fallback(
        self,
        session_id: str,
        llm: Any,
        messages: list[dict[str, Any]],
        gateway: Any | None,
        performed_actions: list[dict[str, Any]],
    ) -> None:
        """One tool-free completion so an exhausted loop still answers."""
        messages.append({
            "role": "system",
            "content": (
                "Bạn đã dùng hết số bước cho phép. Trả lời người dùng ngay bằng lời, "
                "dựa trên dữ liệu đã thu thập. Không gọi tool."
            ),
        })
        try:
            response = await llm.chat(messages, tools=None)
            text = await self._stream_final(gateway, response)
        except (LLMUnavailableError, GarbledOutputError):
            text = ""

        if not text.strip():
            text = (
                "Câu này hơi nhiều phần một lúc nên mình chưa gom đủ dữ liệu. "
                "Bạn hỏi lại từng ý một giúp mình nhé?"
            )
            if gateway is not None:
                await gateway.send_token(text)

        await self._append_turn(session_id, "assistant", text)
        if gateway is not None:
            await gateway.send_done(text, performed_actions)

    def _schedule_memory_update(self, session_id: str) -> None:
        """Consolidate memory in the background once a turn is answered.

        Fire-and-forget: the user already has their reply, and a summarisation
        failure must never surface as a chat error. A strong reference to the
        task is kept so the event loop does not garbage-collect it mid-flight.
        """
        updater = getattr(self.memory, "updateRollingSummary", None)
        if updater is None:
            return

        async def _run() -> None:
            try:
                await updater(session_id, self.llm)
            except Exception as exc:  # pragma: no cover - best effort by design
                logger.debug("Background memory update skipped: %s", exc)

        with contextlib.suppress(RuntimeError):
            task = asyncio.create_task(_run())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    def _build_messages(
        self, context: Any, user_text: str, plan: TurnPlan | None = None
    ) -> list[dict[str, Any]]:
        plan = plan or classify_turn(user_text, history_len=len(context.history))
        prompt = buildSystemPrompt(
            context.rolling_summary,
            context.pinned_facts,
            context.rag_chunks,
            tool_catalog=self.tools if plan.offer_tools else None,
            mode=plan.prompt_mode,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]

        # Chit-chat does not need the tool transcript; dropping it keeps the
        # prompt small and stops the model from re-reading stale tool output.
        include_tools = plan.offer_tools
        for turn in context.history:
            if not include_tools and turn.role == "tool":
                continue
            msg: dict[str, Any] = {"role": turn.role, "content": turn.content}
            if turn.role == "tool" and turn.tool_call_id:
                msg["tool_call_id"] = turn.tool_call_id
            messages.append(msg)
        messages.append({"role": "user", "content": user_text})
        return messages

    async def _stream_final(self, gateway: Any | None, response: Any) -> str:
        chunks: list[str] = []
        if response.content_stream is None:
            return response.full_text or ""
        async for token in response.content_stream:
            chunks.append(token)
            if gateway is not None:
                await gateway.send_token(token)
        return "".join(chunks) or response.full_text or ""

    async def _append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        append = getattr(self.session_store, "appendTurn", None)
        if append is not None:
            result = append(session_id, role, content, tool_call_id, tool_name)
            if hasattr(result, "__await__"):
                await result
            return
        append = getattr(self.session_store, "append_turn", None)
        if append is not None:
            append(session_id, role, content, tool_call_id, tool_name)

    @staticmethod
    def _call_to_message(call: ToolCall) -> dict[str, Any]:
        return {"id": call.id, "function": {"name": call.name, "arguments": call.arguments}}

    @staticmethod
    def _serialize_result(call: ToolCall, result: ToolResult) -> str:
        """Serialise a tool result, attaching recovery guidance on failure."""
        if result.ok:
            return json.dumps({"ok": True, "data": result.data}, ensure_ascii=False)
        code = result.error or "TOOL_INTERNAL_ERROR"
        return json.dumps(
            {
                "ok": False,
                "error": code,
                "tool": call.name,
                "huong_dan": _ERROR_GUIDANCE.get(code, _ERROR_GUIDANCE["TOOL_INTERNAL_ERROR"]),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _summarize_result(result: ToolResult) -> str:
        if not result.ok:
            return result.error or "ERROR"
        text = json.dumps(result.data, ensure_ascii=False)
        return text[:200]


__all__ = ["AgentOrchestrator"]
