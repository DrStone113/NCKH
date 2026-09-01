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
import time
from typing import Any

from config import settings
from services.agent.llm_client import GarbledOutputError, LLMUnavailableError, ToolCall
from services.agent.system_prompt import buildSystemPrompt
from services.agent.tool_dispatcher import ToolResult
from services.agent.turn_router import TurnPlan, classify_turn
from services.agent.context_trace import ContextTraceRecorder
from services.agent.context_planner import ContextPlanner
from services.agent.context_planner.validation.collector import get_natural_collector
from services.agent.context_planner.validation.token_measurement import TokenCounter, measure_turn_tokens
from services.agent.public_reasoning_trace import (
    PublicReasoningTrace,
    record_initial_context,
    record_tool_result,
    record_tool_started,
)
from services.agent.debug_trace import (
    DebugTraceBuilder,
    classify_provider_token,
    elapsed_ms,
)
from services.agent.pending_user_action import PendingActionResolution, PendingUserAction, PendingUserActionStore, pending_user_actions

logger = logging.getLogger(__name__)
_shadow_context_planner = ContextPlanner()


# Guidance handed to the model when a tool call fails, keyed by the stable
# error codes from ``ToolDispatcher``. Without this the model sees an opaque
# code and falls back on "hệ thống đang lỗi", which is exactly the behaviour
_ERROR_GUIDANCE: dict[str, str] = {
    "NO_DISH_FOUND": (
        "Không tìm thấy món ăn nào trong cơ sở dữ liệu phù hợp với yêu cầu này. "
        "Hãy thông báo trung thực, rõ ràng cho người dùng rằng trong database chưa có món ăn khớp tiêu chí "
        "và đề xuất họ thử tìm món khác hoặc đổi tiêu chí. TUYỆT ĐỐI KHÔNG tự bịa ra tên món ăn hay số liệu calo ảo."
    ),
    "NO_WORKOUT_FOUND": (
        "Không tìm thấy bài tập phù hợp trong thư viện ứng dụng. "
        "Hãy thông báo trung thực rằng hiện chưa có bài tập khớp tiêu chí này trong ứng dụng."
    ),
    "NO_FOOD_FOUND": (
        "Không tìm thấy thực phẩm này trong cơ sở dữ liệu dinh dưỡng. "
        "Hãy thông báo rõ ràng cho người dùng biết là chưa có dữ liệu dinh dưỡng cho món/nguyên liệu này."
    ),
    "UNKNOWN_TOOL": (
        "Tool này không tồn tại trong danh sách. Chỉ sử dụng các tool thực tế đã được cung cấp."
    ),
    "INVALID_ARGS": (
        "Tham số sai định dạng. Đọc lại schema của tool và gọi lại đúng một lần với tham số hợp lệ."
    ),
    "TIMEOUT": (
        "Không thể tải dữ liệu do quá thời gian chờ. Hãy thông báo rõ ràng là chưa lấy được thông tin này, "
        "tuyệt đối không tự suy diễn số liệu."
    ),
    "DISCONNECTED": (
        "Ứng dụng tạm thời không phản hồi. Hãy thông báo chưa lấy được dữ liệu này."
    ),
    "TOOL_INTERNAL_ERROR": (
        "Công cụ gặp sự cố khi xử lý dữ liệu. Thông báo trung thực rằng chưa xử lý được mục này, "
        "tuyệt đối không bịa đặt thông tin."
    ),
    "READ_ERROR": (
        "Không đọc được dữ liệu hiện tại từ nguồn lưu trữ. Hãy nói rõ dữ liệu chưa khả dụng; "
        "không dùng snapshot cũ như thể đó là dữ liệu mới."
    ),
    "WRITE_REJECTED": (
        "Yêu cầu ghi bị từ chối trước khi lưu. Không được nói đã lưu; hãy giải thích ngắn gọn "
        "rằng dữ liệu chưa được ghi nhận."
    ),
    "PERSISTENCE_ERROR": (
        "Nguồn lưu trữ không xác nhận được thao tác ghi. Tuyệt đối không nói 'đã lưu' hoặc "
        "'đã ghi nhận'; hãy thông báo thao tác thất bại."
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
        pending_actions: PendingUserActionStore | None = None,
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
        self.pending_actions = pending_actions or pending_user_actions
        self._background_tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------ main
    async def handleChatMessage(
        self, session_id: str, user_text: str, user_context: Any = None
    ) -> None:
        gateway = self.gateway
        public_trace = PublicReasoningTrace()
        record_initial_context(public_trace, user_context)
        debug_trace = DebugTraceBuilder(
            enabled=bool(gateway is not None and getattr(gateway, "debug_trace_enabled", False))
        )
        await self._record_debug(
            gateway,
            debug_trace,
            "lifecycle",
            "orchestrator",
            "TURN_STARTED",
            payload={"session_id": session_id},
        )
        trace = ContextTraceRecorder(
            user_text,
            enabled=(settings.context_trace_enabled or settings.context_planner_shadow_enabled),
        )
        trace.capture_initial_context(user_context)
        try:
            if gateway is not None and hasattr(gateway, "send_status"):
                await gateway.send_status("🔍 Đang tải ngữ cảnh và phân tích câu hỏi...")
            context = await self.memory.loadContext(session_id, user_text)
            trace.capture_rag(context)
            await self._publish_public_trace(gateway, public_trace)
            
            if gateway is not None and hasattr(gateway, "send_status"):
                await gateway.send_status("🧠 Đang lập kế hoạch phản hồi...")
            plan = classify_turn(user_text, history_len=len(context.history))
            await self._record_debug(
                gateway,
                debug_trace,
                "routing",
                "turn_router",
                "ROUTER_DECISION",
                payload={
                    "tier": plan.tier,
                    "uses_heavy_model": plan.use_heavy_model,
                    "offers_tools": plan.offer_tools,
                    "max_steps": plan.max_steps,
                },
            )
            llm = self._select_llm(plan)
            tool_schemas = self.tools.schemas() if plan.offer_tools else None
            trace.capture_tools_offered(tool_schemas)

            logger.info(
                "Turn routed tier=%s heavy=%s tools=%s session=%s",
                plan.tier,
                plan.use_heavy_model,
                bool(tool_schemas),
                session_id,
            )

            user_profile: Any = user_context
            messages = self._build_messages(context, user_text, plan, user_profile=user_profile)
            current_context_size = len(json.dumps(messages, ensure_ascii=False, default=str))
            if tool_schemas:
                current_context_size += len(json.dumps(tool_schemas, ensure_ascii=False, default=str))
            trace.capture_production_router(plan, context_size_characters=current_context_size)
            if settings.context_planner_shadow_enabled:
                # Fail-open observation: D3.0 output cannot become an input to
                # any authoritative production decision in this turn.
                try:
                    names_method = getattr(self.tools, "names", None)
                    available_names = names_method() if callable(names_method) else ()
                    shadow_result = _shadow_context_planner.plan_shadow(
                        user_text, user_context=user_context, memory_context=context,
                        available_tool_names=available_names,
                        current_production_context_size_characters=current_context_size,
                    )
                    trace.capture_shadow(shadow_result)
                    all_tool_schemas = tool_schemas if tool_schemas is not None else self.tools.schemas()
                    token_measurements = measure_turn_tokens(
                        messages=messages,
                        production_tool_schemas=tool_schemas,
                        shadow_bundle=shadow_result.bundle.to_dict(),
                        shadow_tool_names=shadow_result.plan.permitted_tools,
                        all_tool_schemas=all_tool_schemas,
                        counter=TokenCounter.from_llm(llm, settings.llm_model),
                    )
                    trace.capture_token_measurements(token_measurements)
                    collection_path = settings.context_planner_natural_collection_path
                    if collection_path:
                        history = (
                            turn.content for turn in getattr(context, "history", ())
                            if getattr(turn, "role", None) == "user"
                        )
                        get_natural_collector(collection_path).collect(
                            session_id=session_id, query=user_text,
                            conversational_context=history,
                            shadow_result=shadow_result,
                            token_measurements=token_measurements,
                        )
                except Exception:
                    logger.warning("Shadow context planner failed; production turn unchanged", exc_info=True)
            await self._append_turn(session_id, "user", user_text)

            pending_resolution = self.pending_actions.claim_confirmation(
                session_id,
                self._owner_user_id(gateway, user_context),
                user_text,
            )
            if pending_resolution.status != "NO_MATCH":
                if pending_resolution.status == "CLAIMED" and pending_resolution.action is not None:
                    pending_action = pending_resolution.action
                else:
                    await self._respond_to_pending_resolution(
                        session_id,
                        pending_resolution,
                        gateway,
                        public_trace,
                        debug_trace,
                    )
                    trace.finish(outcome=f"PENDING_ACTION_{pending_resolution.status}")
                    self._schedule_memory_update(session_id)
                    return
                await self._resolve_pending_user_action(
                    session_id,
                    pending_action,
                    gateway,
                    public_trace,
                    debug_trace,
                )
                trace.finish(outcome="COMPLETED_PENDING_ACTION")
                self._schedule_memory_update(session_id)
                return

            # The router proposes a per-turn budget; the constructor's
            # ``max_steps`` remains a hard ceiling so callers (and tests) keep
            # full control over the worst case.
            step_budget = max(1, min(plan.max_steps, self.max_steps))

            # Tracks how many times each tool already failed this turn, so a
            # broken tool cannot spin the loop until max_steps runs out.
            failure_counts: dict[str, int] = {}
            workout_structured: dict[str, Any] | None = None
            plan_structured: dict[str, Any] | None = None
            pending_dish_action: PendingUserAction | None = None
            pending_plan_action: PendingUserAction | None = None

            for step in range(step_budget):
                if gateway is not None and hasattr(gateway, "send_status"):
                    if step > 0:
                        await gateway.send_status(f"💭 Đang suy nghĩ bước {step + 1}...")
                    else:
                        await gateway.send_status("🤖 Đang suy nghĩ câu trả lời...")
                llm_started_at = time.perf_counter()
                response = await llm.chat(messages, tools=tool_schemas, prefill=None)
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "provider",
                    "llm_adapter",
                    "RESPONSE_RECEIVED",
                    payload={"tool_call_count": len(response.tool_calls or [])},
                    latency_ms=elapsed_ms(llm_started_at),
                    result="OK",
                )
                full_response = await self._stream_final(gateway, response, debug_trace)

                if not response.tool_calls:
                    if workout_structured is not None:
                        # The numeric plan is never regenerated or paraphrased
                        # by the model.  A deterministic text/card pair wins
                        # over any streamed conversational wording.
                        full_response = str(workout_structured.get("text") or full_response)
                    elif plan_structured is not None:
                        # Plan cards are rendered from the exact immutable
                        # revision, never regenerated as markdown by the LLM.
                        full_response = str(plan_structured.get("text") or full_response)
                    if pending_dish_action is not None:
                        self.pending_actions.put(pending_dish_action)
                        full_response = self._add_confirmation_invitation(
                            full_response, pending_dish_action.display_name
                        )
                        await self._record_debug(
                            gateway,
                            debug_trace,
                            "action",
                            "pending_user_action",
                            "PENDING_ACTION_CREATED",
                            payload={
                                "action_id": pending_dish_action.action_id,
                                "action_type": pending_dish_action.action_type,
                                "target_id": pending_dish_action.target_id,
                            },
                            correlation_id=pending_dish_action.action_id,
                            result="PENDING_CONFIRMATION",
                        )
                        if gateway is not None and hasattr(gateway, "send_action_state"):
                            await gateway.send_action_state(
                                {
                                    "status": "PENDING_CONFIRMATION",
                                    "label": "Chờ bạn xác nhận để lưu món đã gợi ý.",
                                }
                            )
                    if pending_plan_action is not None:
                        self.pending_actions.put(pending_plan_action)
                        full_response = self._add_plan_confirmation_invitation(
                            full_response, pending_plan_action.display_name
                        )
                        await self._record_debug(
                            gateway,
                            debug_trace,
                            "action",
                            "pending_user_action",
                            "PENDING_ACTION_CREATED",
                            payload={
                                "action_id": pending_plan_action.action_id,
                                "action_type": pending_plan_action.action_type,
                                "target_id": pending_plan_action.target_id,
                                "target_identity": pending_plan_action.target_identity,
                            },
                            correlation_id=pending_plan_action.action_id,
                            result="PENDING_CONFIRMATION",
                        )
                        if gateway is not None and hasattr(gateway, "send_action_state"):
                            await gateway.send_action_state(
                                {
                                    "status": "PENDING_CONFIRMATION",
                                    "label": "Chờ bạn xác nhận để lưu đúng phiên bản kế hoạch đang xem.",
                                }
                            )
                    if full_response.strip():
                        public_trace.mark_completed()
                        await self._append_turn(
                            session_id,
                            "assistant",
                            full_response,
                            structured_data=workout_structured,
                            public_trace=self._public_trace_payload(public_trace),
                        )
                    if gateway is not None:
                        await self._send_done(
                            gateway,
                            full_response,
                            structured_data=workout_structured,
                            public_trace=public_trace,
                        )
                    trace.finish(outcome="COMPLETED")
                    self._schedule_memory_update(session_id)
                    return

                if full_response.strip():
                    await self._append_turn(session_id, "assistant", full_response)

                msg: dict[str, Any] = {"role": "assistant"}
                if full_response.strip():
                    msg["content"] = full_response
                msg["tool_calls"] = [self._call_to_message(c) for c in response.tool_calls]
                messages.append(msg)

                if gateway is not None and hasattr(gateway, "send_status"):
                    await gateway.send_status("Đang xử lý dữ liệu cần thiết...")

                for call in response.tool_calls:
                    record_tool_started(public_trace, call.name)
                    await self._record_debug(
                        gateway,
                        debug_trace,
                        "tool",
                        "tool_dispatcher",
                        "TOOL_CALL",
                        payload=self._debug_tool_call_payload(call),
                        correlation_id=call.id,
                    )
                await self._publish_public_trace(gateway, public_trace)

                dispatch_started_at = time.perf_counter()
                tool_results = await self._dispatch_all(
                    session_id, response.tool_calls, failure_counts
                )
                for call in response.tool_calls:
                    trace.capture_tool_call(call.name, call.arguments)

                if gateway is not None and hasattr(gateway, "send_status"):
                    await gateway.send_status("✅ Đã xử lý xong dữ liệu công cụ. Đang tổng hợp phản hồi...")

                for call, result in tool_results:
                    trace.capture_tool_result(call.name, result)
                    record_tool_result(public_trace, call.name, ok=result.ok)
                    await self._record_debug(
                        gateway,
                        debug_trace,
                        "tool",
                        "tool_dispatcher",
                        "TOOL_RESULT",
                        payload=self._debug_tool_result_payload(call, result),
                        correlation_id=call.id,
                        latency_ms=elapsed_ms(dispatch_started_at),
                        result="OK" if result.ok else "ERROR",
                    )
                    if call.name in {
                        "build_personalized_workout",
                        "suggest_workout",
                    } and result.ok and isinstance(result.data, dict):
                        presentation = result.data.get("presentation")
                        if isinstance(presentation, dict) and presentation.get("type") == "personalized_workout":
                            workout_structured = presentation
                            trace.capture_workout_integration(result.data, presentation_path="DETERMINISTIC_CARD")
                    if call.name in {
                        "build_nutrition_plan",
                        "build_workout_schedule",
                        "get_plan",
                        "get_active_plan_v2",
                        "revise_plan",
                    } and result.ok and isinstance(result.data, dict):
                        presentation = result.data.get("presentation")
                        if isinstance(presentation, dict) and presentation.get("type") == "versioned_plan":
                            plan_structured = presentation
                    serialized = self._serialize_result(call, result)
                    await self._append_turn(
                        session_id, "tool", serialized,
                        tool_call_id=call.id, tool_name=call.name,
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": serialized}
                    )
                    ui_message = result.ui_message
                    if isinstance(ui_message, dict):
                        ui_text = ui_message.get("text")
                        structured_data = ui_message.get("structured")
                        if isinstance(ui_text, str) and isinstance(
                            structured_data, dict
                        ):
                            await self._append_turn(
                                session_id,
                                "assistant",
                                ui_text,
                                structured_data=structured_data,
                            )
                    if call.name == "get_user_profile" and result.ok and result.data:
                        if isinstance(user_profile, dict) and isinstance(result.data, dict):
                            user_profile = {**user_profile, **result.data}
                        else:
                            user_profile = result.data
                    if (
                        call.name == "suggest_dish"
                        and result.ok
                        and isinstance(result.data, dict)
                    ):
                        pending_dish_action = self.pending_actions.create_dish_log_action(
                            session_id,
                            owner_user_id=self._owner_user_id(gateway, user_context),
                            suggestion=result.data,
                            suggestion_arguments=call.arguments,
                        )
                    if (
                        call.name in {"build_nutrition_plan", "build_workout_schedule", "revise_plan"}
                        and result.ok
                        and isinstance(result.data, dict)
                        and result.data.get("status") == "READY"
                    ):
                        pending_plan_action = self.pending_actions.create_plan_save_action(
                            session_id,
                            owner_user_id=self._owner_user_id(gateway, user_context),
                            plan_payload=result.data,
                        )

                await self._publish_public_trace(gateway, public_trace)

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
                        relevant_history=getattr(context, "relevant_history", None),
                    )

                # Last permitted step: force a text answer instead of dying on
                # AGENT_LOOP_EXCEEDED, which the user reads as a crash.
                if step == step_budget - 2:
                    messages.append({
                        "role": "user",
                        "content": (
                            "[HỆ THỐNG: Đã đủ dữ liệu. Trả lời người dùng bằng lời ngay bây giờ, "
                            "không gọi thêm tool nào nữa.]"
                        ),
                    })

            # Loop exhausted — make one last tool-free pass so the user still
            # gets a real answer.
            await self._final_answer_fallback(
                session_id,
                llm,
                messages,
                gateway,
                public_trace,
                debug_trace,
                workout_structured,
                pending_dish_action,
                plan_structured,
                pending_plan_action,
            )
            trace.finish(outcome="COMPLETED_WITH_FALLBACK")
            self._schedule_memory_update(session_id)

        except LLMUnavailableError:
            trace.finish(outcome="LLM_UNAVAILABLE")
            logger.warning("LLM unavailable for session=%s", session_id, exc_info=True)
            if gateway is not None:
                await gateway.send_error(
                    "LLM_UNAVAILABLE",
                    "Mình chưa kết nối được tới máy chủ AI. Bạn thử lại sau ít phút nhé.",
                )
            raise
        except GarbledOutputError:
            trace.finish(outcome="LLM_ERROR")
            logger.warning("Garbled LLM output for session=%s", session_id)
            if gateway is not None:
                await gateway.send_error(
                    "LLM_ERROR",
                    "Phản hồi bị lỗi ký tự. Bạn nhắn lại giúp mình nhé.",
                )
            raise
        finally:
            if not trace.trace.final_context_manifest:
                trace.finish(outcome="ERROR")
            trace.emit()

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
        public_trace: PublicReasoningTrace,
        debug_trace: DebugTraceBuilder,
        workout_structured: dict[str, Any] | None = None,
        pending_dish_action: PendingUserAction | None = None,
        plan_structured: dict[str, Any] | None = None,
        pending_plan_action: PendingUserAction | None = None,
    ) -> None:
        """One tool-free completion so an exhausted loop still answers."""
        messages.append({
            "role": "user",
            "content": (
                "[HỆ THỐNG: Bạn đã dùng hết số bước cho phép. Trả lời người dùng ngay bằng lời, "
                "dựa trên dữ liệu đã thu thập. Không gọi tool.]"
            ),
        })
        try:
            llm_started_at = time.perf_counter()
            response = await llm.chat(messages, tools=None)
            await self._record_debug(
                gateway,
                debug_trace,
                "provider",
                "llm_adapter",
                "FALLBACK_RESPONSE_RECEIVED",
                payload={"tool_call_count": len(response.tool_calls or [])},
                latency_ms=elapsed_ms(llm_started_at),
                result="OK",
            )
            text = await self._stream_final(gateway, response, debug_trace)
        except (LLMUnavailableError, GarbledOutputError):
            text = ""

        if workout_structured is not None:
            text = str(workout_structured.get("text") or text)
        elif plan_structured is not None:
            text = str(plan_structured.get("text") or text)
        elif not text.strip():
            text = (
                "Câu này hơi nhiều phần một lúc nên mình chưa gom đủ dữ liệu. "
                "Bạn hỏi lại từng ý một giúp mình nhé?"
            )
            if gateway is not None:
                await gateway.send_token(text)

        if pending_dish_action is not None:
            self.pending_actions.put(pending_dish_action)
            text = self._add_confirmation_invitation(
                text, pending_dish_action.display_name
            )
            await self._record_debug(
                gateway,
                debug_trace,
                "action",
                "pending_user_action",
                "PENDING_ACTION_CREATED",
                payload={
                    "action_id": pending_dish_action.action_id,
                    "action_type": pending_dish_action.action_type,
                    "target_id": pending_dish_action.target_id,
                },
                correlation_id=pending_dish_action.action_id,
                result="PENDING_CONFIRMATION",
            )
        if pending_plan_action is not None:
            self.pending_actions.put(pending_plan_action)
            text = self._add_plan_confirmation_invitation(
                text, pending_plan_action.display_name
            )
            await self._record_debug(
                gateway,
                debug_trace,
                "action",
                "pending_user_action",
                "PENDING_ACTION_CREATED",
                payload={
                    "action_id": pending_plan_action.action_id,
                    "action_type": pending_plan_action.action_type,
                    "target_id": pending_plan_action.target_id,
                    "target_identity": pending_plan_action.target_identity,
                },
                correlation_id=pending_plan_action.action_id,
                result="PENDING_CONFIRMATION",
            )

        public_trace.mark_completed()
        await self._append_turn(
            session_id,
            "assistant",
            text,
            structured_data=plan_structured or workout_structured,
            public_trace=self._public_trace_payload(public_trace),
        )
        if gateway is not None:
            await self._send_done(
                gateway,
                text,
                structured_data=plan_structured or workout_structured,
                public_trace=public_trace,
            )

    async def _resolve_pending_user_action(
        self,
        session_id: str,
        action: PendingUserAction,
        gateway: Any | None,
        public_trace: PublicReasoningTrace,
        debug_trace: DebugTraceBuilder,
    ) -> None:
        """Execute the exact stored action without asking the LLM again."""

        public_trace.add("CONFIRMATION_RECEIVED")
        record_tool_started(public_trace, action.tool_name)
        call = ToolCall(
            id=action.action_id,
            name=action.tool_name,
            arguments=action.tool_arguments,
        )
        await self._record_debug(
            gateway,
            debug_trace,
            "action",
            "pending_user_action",
            "USER_CONFIRMATION",
            payload={"affirmative": True, "target_id": action.target_id},
            correlation_id=action.action_id,
            result="CONFIRMED",
        )
        await self._record_debug(
            gateway,
            debug_trace,
            "action",
            "pending_user_action",
            "ACTION_RESOLUTION",
            payload={
                "action_id": action.action_id,
                "action_type": action.action_type,
                "target_id": action.target_id,
            },
            correlation_id=action.action_id,
            result="CONFIRMED",
        )
        await self._record_debug(
            gateway,
            debug_trace,
            "tool",
            "tool_dispatcher",
            "TOOL_CALL",
            payload=self._debug_tool_call_payload(call),
            correlation_id=action.action_id,
        )
        started_at = time.perf_counter()
        result = await self.dispatcher.dispatch(session_id, call, self.tool_timeout_ms)
        record_tool_result(public_trace, action.tool_name, ok=result.ok)
        await self._record_debug(
            gateway,
            debug_trace,
            "persistence",
            "tool_dispatcher",
            "DB_WRITE",
            payload=self._debug_tool_result_payload(call, result),
            correlation_id=action.action_id,
            latency_ms=elapsed_ms(started_at),
            result="PERSISTED" if result.ok else "NOT_PERSISTED",
        )

        structured_data: dict[str, Any] | None = None
        result_data = result.data if isinstance(result.data, dict) else {}
        identity = self._pending_action_identity(action, result)
        identity_verified = identity["verified"]
        if identity_verified and self.pending_actions.complete(
            action,
            persisted_reference_id=str(identity["persisted_reference_id"]),
        ):
            await self._record_debug(
                gateway,
                debug_trace,
                "persistence",
                "tool_dispatcher",
                "READ_BACK",
                payload={
                    "target_id": action.target_id,
                    **identity["debug_references"],
                },
                correlation_id=action.action_id,
                result="IDENTITY_VERIFIED",
            )
            public_trace.mark_completed()
            if action.action_type == "SAVE_PLAN_REVISION" and result_data.get("write_status") == "SHADOW_SAVED":
                text = (
                    f"Đã xác nhận {action.display_name} trong chế độ thử nghiệm. "
                    "Bản này chưa thay thế kế hoạch production đang dùng."
                )
            elif action.action_type == "SAVE_PLAN_REVISION":
                text = f"Đã lưu {action.display_name}."
            else:
                text = f"Đã lưu {action.display_name} vào nhật ký của bạn."
            if isinstance(result.ui_message, dict):
                candidate = result.ui_message.get("structured")
                if isinstance(candidate, dict):
                    structured_data = candidate
            if structured_data is None:
                candidate = result_data.get("presentation")
                if isinstance(candidate, dict) and candidate.get("type") == "versioned_plan":
                    structured_data = candidate
            state = {
                "status": "PERSISTED",
                "label": "Đã lưu lựa chọn bạn vừa xác nhận.",
            }
        else:
            # A write acknowledgement without the catalogue identity chain is
            # deliberately not presented as saved. Release the claim so the
            # user can retry after the client reports a real persistence error.
            self.pending_actions.release(action)
            public_trace.mark_clarification_required()
            if result.ok:
                text = (
                    f"Mình chưa xác minh được {action.display_name} đã được lưu đúng. "
                    "Bạn vui lòng thử lại nhé."
                )
            else:
                text = (
                    f"Mình chưa thể lưu {action.display_name}. "
                    "Bạn có thể xác nhận lại hoặc thử lại sau nhé."
                )
            state = {
                "status": "NOT_PERSISTED",
                "label": "Chưa lưu được lựa chọn đã xác nhận.",
            }

        await self._append_turn(
            session_id,
            "assistant",
            text,
            structured_data=structured_data,
            public_trace=self._public_trace_payload(public_trace),
        )
        if gateway is not None and hasattr(gateway, "send_action_state"):
            await gateway.send_action_state(state)
        if gateway is not None:
            await self._send_done(
                gateway,
                text,
                structured_data=structured_data,
                public_trace=public_trace,
            )

    async def _respond_to_pending_resolution(
        self,
        session_id: str,
        resolution: PendingActionResolution,
        gateway: Any | None,
        public_trace: PublicReasoningTrace,
        debug_trace: DebugTraceBuilder,
    ) -> None:
        """Reply safely to a terminal or ambiguous confirmation attempt.

        These branches intentionally do not invoke the LLM or dispatcher. A
        plain confirmation must never select an arbitrary pending write.
        """

        action = resolution.action
        await self._record_debug(
            gateway,
            debug_trace,
            "action",
            "pending_user_action",
            "ACTION_RESOLUTION",
            payload={
                "status": resolution.status,
                "target_id": action.target_id if action is not None else None,
            },
            correlation_id=action.action_id if action is not None else None,
            result=resolution.status,
        )
        structured_data: dict[str, Any] | None = None
        if resolution.status == "ALREADY_EXECUTED":
            public_trace.add("CONFIRMATION_RECEIVED")
            public_trace.add("PERSISTENCE_CONFIRMED")
            public_trace.mark_completed()
            text = "Lựa chọn này đã được lưu trước đó, nên mình không ghi thêm lần nữa."
            state = {
                "status": "ALREADY_EXECUTED",
                "label": "Lựa chọn này đã được lưu trước đó.",
            }
        elif resolution.status == "IN_PROGRESS":
            public_trace.add("CONFIRMATION_RECEIVED")
            public_trace.add("PERSISTENCE_IN_PROGRESS")
            text = "Lựa chọn này đang được lưu. Mình sẽ không tạo thêm một bản ghi nữa."
            state = {
                "status": "IN_PROGRESS",
                "label": "Đang lưu lựa chọn bạn vừa xác nhận.",
            }
        elif resolution.status == "AMBIGUOUS":
            public_trace.mark_clarification_required()
            text = (
                "Bạn đang có vài lựa chọn chờ xác nhận. Hãy nói rõ tên món hoặc "
                "yêu cầu lại lựa chọn bạn muốn lưu nhé."
            )
            state = {
                "status": "CLARIFICATION_REQUIRED",
                "label": "Cần xác định rõ lựa chọn cần lưu.",
            }
        elif resolution.status == "ACTION_EXPIRED":
            public_trace.mark_clarification_required()
            text = "Xác nhận này đã hết hạn. Bạn hãy yêu cầu gợi ý lại để mình kiểm tra thông tin mới nhất nhé."
            state = {
                "status": "ACTION_EXPIRED",
                "label": "Lựa chọn chờ xác nhận đã hết hạn.",
            }
        else:  # OWNER_MISMATCH and future non-action statuses
            public_trace.mark_clarification_required()
            text = "Mình không tìm thấy lựa chọn chờ xác nhận cho phiên này. Bạn hãy yêu cầu lại nếu vẫn muốn lưu nhé."
            state = {
                "status": "NO_PENDING_ACTION",
                "label": "Không có lựa chọn phù hợp để lưu.",
            }

        await self._append_turn(
            session_id,
            "assistant",
            text,
            structured_data=structured_data,
            public_trace=self._public_trace_payload(public_trace),
        )
        if gateway is not None and hasattr(gateway, "send_action_state"):
            await gateway.send_action_state(state)
        if gateway is not None:
            await self._send_done(
                gateway,
                text,
                structured_data=structured_data,
                public_trace=public_trace,
            )

    @staticmethod
    def _owner_user_id(gateway: Any | None, user_context: Any | None) -> str:
        """Resolve a stable principal for pending-action ownership.

        Authenticated gateway identity wins over caller-provided context. The
        anonymous fallback keeps local/offline development deterministic while
        still binding the action to a single session.
        """

        gateway_user_id = getattr(gateway, "user_id", None) if gateway is not None else None
        if isinstance(gateway_user_id, str) and gateway_user_id.strip():
            return gateway_user_id.strip()
        if isinstance(user_context, dict):
            for key in ("user_id", "id"):
                value = user_context.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return "anonymous"

    @staticmethod
    def _add_confirmation_invitation(text: str, display_name: str) -> str:
        invitation = f"Bạn có muốn lưu **{display_name}** vào nhật ký không?"
        if invitation in text:
            return text
        return f"{text.rstrip()}\n\n{invitation}".strip()

    @staticmethod
    def _add_plan_confirmation_invitation(text: str, display_name: str) -> str:
        invitation = f"Bạn có muốn lưu đúng **{display_name}** này không?"
        if invitation in text:
            return text
        return f"{text.rstrip()}\n\n{invitation}".strip()

    def _pending_action_identity(
        self, action: PendingUserAction, result: ToolResult
    ) -> dict[str, Any]:
        """Verify a stored action against its domain-specific read-back chain."""

        data = result.data if isinstance(result.data, dict) else {}
        if action.action_type == "SAVE_PLAN_REVISION":
            expected = action.target_identity
            persisted = {
                "plan_id": data.get("plan_id"),
                "revision_id": data.get("revision_id"),
                "revision_content_hash": data.get("revision_content_hash"),
            }
            read_back = {
                "plan_id": data.get("read_back_plan_id"),
                "revision_id": data.get("read_back_revision_id"),
                "revision_content_hash": data.get("read_back_revision_content_hash"),
            }
            verified = (
                result.ok
                and data.get("write_status") in {"SHADOW_SAVED", "PERSISTED"}
                and expected == persisted
                and expected == read_back
            )
            return {
                "verified": verified,
                "persisted_reference_id": read_back.get("revision_id"),
                "debug_references": {
                    "expected_plan_id": expected.get("plan_id"),
                    "expected_revision_id": expected.get("revision_id"),
                    "persisted_plan_id": persisted.get("plan_id"),
                    "persisted_revision_id": persisted.get("revision_id"),
                    "read_back_plan_id": read_back.get("plan_id"),
                    "read_back_revision_id": read_back.get("revision_id"),
                },
            }
        persisted_id = data.get("catalog_dish_id")
        read_back_id = data.get("read_back_catalog_dish_id")
        card_id = self._structured_card_catalog_dish_id(result.ui_message)
        return {
            "verified": (
                result.ok
                and persisted_id == action.target_id
                and read_back_id == action.target_id
                and card_id == action.target_id
            ),
            "persisted_reference_id": read_back_id,
            "debug_references": {
                "persisted_reference_id": persisted_id,
                "read_back_reference_id": read_back_id,
                "card_reference_id": card_id,
            },
        }

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
        self,
        context: Any,
        user_text: str,
        plan: TurnPlan | None = None,
        user_profile: Any = None,
    ) -> list[dict[str, Any]]:
        plan = plan or classify_turn(user_text, history_len=len(context.history))
        prompt = buildSystemPrompt(
            context.rolling_summary,
            context.pinned_facts,
            context.rag_chunks,
            tool_catalog=self.tools if plan.offer_tools else None,
            user_profile=user_profile,
            mode=plan.prompt_mode,
            relevant_history=getattr(context, "relevant_history", None),
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

    async def _stream_final(
        self,
        gateway: Any | None,
        response: Any,
        debug_trace: DebugTraceBuilder,
    ) -> str:
        chunks: list[str] = []
        if response.content_stream is None:
            return response.full_text or ""
        async for token in response.content_stream:
            provider_event_type = classify_provider_token(token)
            if provider_event_type == "INTERNAL_REASONING":
                # Provider reasoning/scratchpad is never sent to or persisted
                # for the user. Public steps come from trusted app events.
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "provider",
                    "llm_adapter",
                    "INTERNAL_REASONING_DROPPED",
                    payload={"provider_event_type": provider_event_type},
                    result="DROPPED",
                )
                continue
            if provider_event_type != "VISIBLE_CONTENT":
                # The adapter has no provider-declared display-safe reasoning
                # summary contract today. Keep metadata for debug, but never
                # pass an unverified provider field into the public channel.
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "provider",
                    "llm_adapter",
                    "TOKEN_USAGE" if provider_event_type == "USAGE" else "PROVIDER_EVENT",
                    payload={"provider_event_type": provider_event_type},
                    result="OBSERVED",
                )
                continue
            else:
                chunks.append(str(token))
                if gateway is not None and hasattr(gateway, "send_token"):
                    await gateway.send_token(str(token))
        return "".join(chunks) or response.full_text or ""

    async def _append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        thoughts: str = "",
        structured_data: dict[str, Any] | None = None,
        public_trace: dict[str, Any] | None = None,
    ) -> None:
        append = getattr(self.session_store, "appendTurn", None)
        if append is not None:
            result = append(
                session_id,
                role,
                content,
                tool_call_id,
                tool_name,
                thoughts,
                structured_data,
                public_trace,
            )
            if hasattr(result, "__await__"):
                await result
            return
        append = getattr(self.session_store, "append_turn", None)
        if append is not None:
            append(
                session_id,
                role,
                content,
                tool_call_id,
                tool_name,
                thoughts,
                structured_data,
                public_trace,
            )

    @staticmethod
    async def _publish_public_trace(
        gateway: Any | None, public_trace: PublicReasoningTrace
    ) -> None:
        if (
            gateway is not None
            and public_trace.steps
            and hasattr(gateway, "send_public_trace")
        ):
            await gateway.send_public_trace(public_trace.to_dict())

    @staticmethod
    def _public_trace_payload(
        public_trace: PublicReasoningTrace,
    ) -> dict[str, Any] | None:
        return public_trace.to_dict() if public_trace.steps else None

    @staticmethod
    async def _record_debug(
        gateway: Any | None,
        debug_trace: DebugTraceBuilder,
        category: str,
        component: str,
        operation: str,
        *,
        payload: Any = None,
        correlation_id: str | None = None,
        latency_ms: float | None = None,
        result: str | None = None,
    ) -> None:
        event = debug_trace.record(
            category,
            component,
            operation,
            payload=payload,
            correlation_id=correlation_id,
            latency_ms=latency_ms,
            result=result,
        )
        if event is not None and gateway is not None and hasattr(gateway, "send_debug_trace"):
            await gateway.send_debug_trace(event.to_dict())

    @staticmethod
    def _debug_tool_call_payload(call: ToolCall) -> dict[str, Any]:
        """Expose tool execution shape without copying user/profile payloads."""

        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        safe_argument_keys = {
            "meal_type",
            "target_kcal",
            "serving_grams",
            "catalog_dish_id",
            "duration_min",
            "plan_id",
            "revision_id",
            "expected_revision_number",
            "operation",
            "domain",
            "period_start",
            "period_end",
            "timezone",
        }
        safe_arguments = {
            key: value
            for key, value in arguments.items()
            if key in safe_argument_keys and isinstance(value, (str, bool, int, float))
        }
        payload: dict[str, Any] = {
            "name": call.name,
            "argument_keys": sorted(str(key) for key in arguments),
        }
        if safe_arguments:
            payload["sanitized_arguments"] = safe_arguments
        catalog_dish_id = arguments.get("catalog_dish_id")
        if isinstance(catalog_dish_id, str) and catalog_dish_id:
            payload["target_id"] = catalog_dish_id
        return payload

    @staticmethod
    def _structured_card_catalog_dish_id(ui_message: Any) -> str | None:
        """Read the reference displayed in a structured meal card, if any."""

        if not isinstance(ui_message, dict):
            return None
        structured = ui_message.get("structured")
        if not isinstance(structured, dict):
            return None
        actions = structured.get("actions")
        if not isinstance(actions, list):
            return None
        card_ids = {
            str(details.get("catalog_dish_id"))
            for action in actions
            if isinstance(action, dict)
            and isinstance((details := action.get("details")), dict)
            and isinstance(details.get("catalog_dish_id"), str)
            and details.get("catalog_dish_id")
        }
        return next(iter(card_ids)) if len(card_ids) == 1 else None

    @staticmethod
    def _debug_tool_result_payload(call: ToolCall, result: ToolResult) -> dict[str, Any]:
        """Expose only result state and safe reference identifiers in debug."""

        data = result.data if isinstance(result.data, dict) else {}
        payload: dict[str, Any] = {
            "name": call.name,
            "ok": result.ok,
            "result_keys": sorted(str(key) for key in data),
        }
        if result.error:
            payload["error_code"] = result.error
        for key in (
            "write_status", "meal_record_status", "catalog_dish_id", "read_back_catalog_dish_id",
            "plan_id", "revision_id", "read_back_plan_id", "read_back_revision_id",
            "lifecycle_status", "status",
        ):
            value = data.get(key)
            if isinstance(value, (str, bool, int, float)):
                payload[key] = value
        return payload

    @staticmethod
    async def _send_done(
        gateway: Any,
        full_response: str,
        *,
        structured_data: dict[str, Any] | None,
        public_trace: PublicReasoningTrace,
    ) -> None:
        await gateway.send_done(
            full_response,
            structured_data=structured_data,
            public_trace=AgentOrchestrator._public_trace_payload(public_trace),
        )

    @staticmethod
    def _call_to_message(call: ToolCall) -> dict[str, Any]:
        """Render a ToolCall as an OpenAI ``assistant.tool_calls`` entry.

        Two details matter and were previously wrong:

        - ``type`` is required by the API schema.
        - ``arguments`` must be a JSON *string*, not an object. Sending a dict
          makes strict providers reject the whole request with HTTP 400
          (``BAD_REQUEST``), which surfaced to users as LLM_UNAVAILABLE on the
          second agent step — i.e. every turn that actually used a tool.
          Lenient providers accepted it, which is why this went unnoticed.
        """
        arguments = call.arguments
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments or {}, ensure_ascii=False)
        return {
            "id": call.id,
            "type": "function",
            "function": {"name": call.name, "arguments": arguments},
        }

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
                "data": result.data,
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
