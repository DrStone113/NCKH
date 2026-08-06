# Requirements Document

> Ngôn ngữ: Tiếng Việt (đồng bộ với `design.md`).
> Đây là tài liệu **dẫn xuất từ design** theo workflow design-first. Mỗi requirement đều có thể truy ngược đến một quyết định trong `design.md`, và mỗi Correctness Property trong `design.md` (§12) đều được ánh xạ về một Acceptance Criterion ở đây qua định danh `X.Y`.

## Introduction

Tài liệu này mô tả các yêu cầu chức năng và phi chức năng cho việc thiết kế lại toàn bộ chatbot trong HealthApp theo kiến trúc **agent có công cụ (tool-using agent)** đã thống nhất trong `design.md`.

Mục tiêu nghiệp vụ: chatbot trở thành một orchestrator duy nhất, có khả năng đọc/ghi dữ liệu thật của user (qua tool client chạy trên Flutter và tool server chạy trên FastAPI), tạo kế hoạch dài hạn nhiều tuần, và duy trì long-term memory hội thoại — thay cho hệ thống fragmented hiện tại (`intent_classifier`, `conversation_flow`, `prompt_builder`, `ai_analyzer`, `response_parser`, `user_state`, ...).

Các nhóm requirement được tổ chức theo đúng phân nhóm mà `design.md` §12 tham chiếu:

- Nhóm 1 — Ổn định / reliability của vòng lặp agent.
- Nhóm 2 — Truy xuất và ghi dữ liệu user qua tool catalog.
- Nhóm 3 — Kế hoạch dài hạn (long-term plan).
- Nhóm 4 — Chất lượng gợi ý món ăn và bài tập.
- Nhóm 5 — Long-term memory hội thoại.
- Nhóm 6 — Giao thức WebSocket và bảo mật.
- Nhóm 7 — Migration code cũ.
- Nhóm 8 — Trải nghiệm hội thoại tiếng Việt.

## Glossary

- **Agent_Orchestrator**: Thành phần backend triển khai vòng lặp ReAct (Reason + Act), gọi LLM, dispatch tool, stream token (xem `design.md` §4.2, §8.1).
- **Chat_Gateway**: Lớp transport WebSocket, nhận `chat_message` / `tool_result`, phát `token` / `tool_call` / `done` / `error` (xem `design.md` §4.1, §7).
- **Tool_Registry**: Đăng ký tool với JSON Schema, side (server/client), timeout, idempotency flag (xem `design.md` §4.3, §9.2).
- **Tool_Dispatcher**: Validate args và thực thi tool (server-side gọi trực tiếp, client-side gửi qua WebSocket và await tool_result theo `correlation_id`) (xem `design.md` §4.3, §8.2).
- **LLM_Client**: Wrapper Ollama `/api/chat` có hỗ trợ `tools` field, streaming, fallback JSON-mode (xem `design.md` §4.4, §9.1).
- **Memory_Service**: Lưu trữ lịch sử hội thoại, rolling summary, pinned facts, RAG retrieval (xem `design.md` §4.5, §9.6).
- **Planner_Agent**: Sub-agent tạo kế hoạch dài hạn theo ngày, gọi tool `suggest_dish` / `suggest_workout` lặp theo ngày và `append_plan_items` (xem `design.md` §3.3, §8.3).
- **Suggest_Dish_Tool**, **Suggest_Workout_Tool**, **Calculate_TDEE_Tool**, **RAG_Service**: Các tool server-side (xem `design.md` §4.6, §9.4–9.6).
- **System_Prompt**: Prompt hệ thống ngắn gọn được build từ `rolling_summary` + `pinned_facts` + `rag_chunks` (xem `design.md` §8.1).
- **Backend**: Toàn bộ FastAPI app sau migration (xem `design.md` §16).
- **Database_Migration**: Tập các `ALTER` / `CREATE` SQL trong §10 của `design.md`.
- **MAX_AGENT_STEPS**: Số lần gọi LLM tối đa trong một turn, mặc định 6 (xem `design.md` §4.2).
- **TOOL_TIMEOUT**: Thời gian chờ tối đa cho một tool, mặc định 15000 ms (xem `design.md` §11.1).
- **SUMMARY_THRESHOLD** / **KEEP_RAW_TURNS**: Hằng số kiểm soát rolling summary (xem `design.md` §8.4).
- **RAG_SIMILARITY_THRESHOLD**: Ngưỡng cosine similarity tối thiểu khi truy xuất RAG (xem `design.md` §9.6).
- **correlation_id**: ID duy nhất gắn vào mỗi `tool_call` để khớp với `tool_result` tương ứng (xem `design.md` §7).
- **request_id**: ID idempotency cho write tool, cho phép retry không tạo bản ghi trùng (xem `design.md` §5).

## Requirements

### Requirement 1: Vòng lặp Agent có công cụ chạy ổn định

**User Story:** Là người dùng cuối, tôi muốn chatbot xử lý mọi câu hỏi (kể cả câu phức tạp cần nhiều bước tool) một cách ổn định và an toàn, để không gặp tình trạng treo, lỗi không kiểm soát, hay vòng lặp vô hạn.

#### Acceptance Criteria

1. IF một `tool_call` có `name` không tồn tại trong `Tool_Registry` hoặc `arguments` không khớp JSON Schema của tool, THEN THE Tool_Dispatcher SHALL trả về `ToolResult(ok=false)` với `error_code` lần lượt là `"UNKNOWN_TOOL"` hoặc `"INVALID_ARGS"` và SHALL NOT để exception thoát ra ngoài Tool_Dispatcher.
2. WHILE Agent_Orchestrator đang xử lý một `chat_message`, THE Agent_Orchestrator SHALL thực hiện không quá `MAX_AGENT_STEPS` (mặc định 6) lần gọi LLM trước khi gửi `done` hoặc `error` qua Chat_Gateway.
3. WHEN một turn kết thúc bằng `done` hoặc `error`, THE Agent_Orchestrator SHALL bảo đảm mọi row trong bảng `tool_invocations` thuộc turn đó có `result IS NOT NULL` hoặc `error_code IS NOT NULL` (không tồn tại tool invocation pending).
4. WHEN một server tool vượt quá `TOOL_TIMEOUT`, THE Tool_Dispatcher SHALL trả `ToolResult(ok=false, error="TIMEOUT")` cho Agent_Orchestrator và SHALL inject kết quả đó vào `messages` để LLM tự xử lý ở vòng lặp tiếp theo.
5. IF Ollama không phản hồi (LLM unavailable), THEN THE Agent_Orchestrator SHALL gửi `error` với `code="LLM_UNAVAILABLE"` qua Chat_Gateway và SHALL NOT retry tự động trong cùng turn.
6. IF LLM trả output chứa ≥ 30% ký tự không hợp lệ (garbled), THEN THE LLM_Client SHALL raise `GarbledOutputError` và THE Agent_Orchestrator SHALL gửi `error` với `code="LLM_ERROR"`.
7. IF WebSocket disconnect khi đang chờ `tool_result` từ client, THEN THE Tool_Dispatcher SHALL trả `ToolResult(ok=false, error="DISCONNECTED")` cho mọi pending future và SHALL xóa entry tương ứng khỏi bảng `pendingCalls`.
8. WHEN Agent_Orchestrator vượt `MAX_AGENT_STEPS` mà LLM vẫn yêu cầu thêm tool, THE Agent_Orchestrator SHALL gửi `error` với `code="AGENT_LOOP_EXCEEDED"`.

### Requirement 2: Truy xuất và ghi dữ liệu user qua Tool Catalog

**User Story:** Là người dùng có dữ liệu cá nhân (profile, nhật ký bữa ăn, bài tập, cân nặng, kế hoạch) lưu trên Flutter, tôi muốn chatbot đọc và ghi đúng dữ liệu thật của tôi qua tool, để có trải nghiệm cá nhân hóa thay vì gợi ý chung chung.

#### Acceptance Criteria

1. WHEN Agent_Orchestrator phát ra `n` `tool_call` trong một turn, THE Chat_Gateway SHALL gán cho mỗi `tool_call` một `correlation_id` duy nhất trong phạm vi turn, và sau khi turn kết thúc, số dòng trong `tool_invocations` thuộc turn đó SHALL bằng `n` với `count(distinct correlation_id) = n`.
2. WHERE tool có `idempotent = true`, WHEN tool đó được gọi hai lần liên tiếp với cùng `arguments` trong cùng `session_id` mà không có write tool xen giữa, THE Tool_Dispatcher SHALL trả về kết quả ngữ nghĩa giống nhau ở cả hai lần gọi.
3. THE Tool_Registry SHALL đăng ký các client tool đọc dữ liệu: `get_user_profile`, `get_today_meals`, `get_today_exercises`, `get_meal_log_range`, `get_exercise_log_range`, `get_weight_history`, `get_active_plan`.
4. THE Tool_Registry SHALL đăng ký các client tool ghi dữ liệu hoặc gây side-effect: `log_meal`, `log_exercise`, `log_weight`, `mark_plan_item_complete`, `navigate_to_screen`.
5. THE Tool_Registry SHALL đăng ký các server tool: `suggest_dish`, `suggest_workout`, `calculate_tdee`, `search_food_nutrition`, `create_plan`, `append_plan_items`, `query_rag`.
6. WHERE tool có `idempotent = false` (write tool), THE Tool_Dispatcher SHALL yêu cầu `arguments` chứa `request_id` và SHALL bỏ qua việc tạo bản ghi trùng nếu nhận lại cùng `request_id` trong cùng `session_id`.
7. IF Chat_Gateway nhận `tool_result` có `correlation_id` không khớp bất kỳ pending `tool_call` nào, THEN THE Chat_Gateway SHALL ghi log và bỏ qua message đó, đồng thời SHALL NOT đóng socket.
8. WHEN client tool `navigate_to_screen` được gọi, THE Tool_Dispatcher SHALL chấp nhận kết quả `{ok: true}` từ client và SHALL coi đây là tool có side-effect (`idempotent=false`).

### Requirement 3: Kế hoạch dài hạn nhiều tuần (Long-term Plan)

**User Story:** Là người dùng theo đuổi một mục tiêu sức khỏe trải dài nhiều tuần (giảm cân, tăng cơ, duy trì), tôi muốn chatbot tạo kế hoạch chi tiết theo từng ngày với món ăn và bài tập cụ thể, để tôi không phải tự lên thực đơn và lịch tập hàng ngày.

#### Acceptance Criteria

1. WHEN Planner_Agent kết thúc tạo plan thành công, FOR ALL `d ∈ [1, plan.duration_days]`, THE Planner_Agent SHALL bảo đảm `sum(plan_items.target_kcal where plan_id = plan.id and item_type = 'meal' and day_index = d)` thuộc khoảng `[0.9 * plan.daily_kcal_target, 1.1 * plan.daily_kcal_target]` (sai số ±10%).
2. WHEN Planner_Agent kết thúc tạo plan thành công, THE Planner_Agent SHALL bảo đảm `set(plan_items.day_index where plan_id = p.id) == {1, 2, ..., p.duration_days}` (không thiếu ngày, không thừa ngày, không trùng `day_index`).
3. IF `duration_days < 3` hoặc `duration_days > 120` hoặc `duration_days` không phải số nguyên, THEN THE Planner_Agent SHALL từ chối tạo plan, trả `error_code = "INVALID_DURATION"`, và SHALL NOT ghi bất kỳ row nào vào bảng `plans` hoặc `plan_items`.
4. THE Plan SHALL thỏa ràng buộc `end_date - start_date + 1 == duration_days` với `duration_days ∈ [3, 120]` và `start_date ≤ end_date`.
5. FOR ALL `plan_items` thuộc cùng một `plan_id = p.id`, THE PlanItem.plan_date SHALL bằng `p.start_date + (day_index - 1)` và `day_index ∈ [1, p.duration_days]`.
6. WHERE một `(plan_id, day_index)` không phải rest day, THE Planner_Agent SHALL tạo từ 3 đến 5 `plan_items` với `item_type = 'meal'` sao cho tập `meal_type` của các item đó chứa đầy đủ ba giá trị `{'breakfast', 'lunch', 'dinner'}` (mỗi giá trị xuất hiện đúng một lần) và mọi item bổ sung (nếu có) đều có `meal_type = 'snack'`; đồng thời SHALL tạo từ 1 đến 2 `plan_items` với `item_type = 'exercise'` cho ngày đó.
7. WHERE một `(plan_id, day_index)` là rest day, THE Planner_Agent SHALL tạo đúng 0 `plan_items` với `item_type = 'exercise'` cho ngày đó, và SHALL vẫn tạo 3 `plan_items` với `item_type = 'meal'` (`breakfast`, `lunch`, `dinner`) cho ngày đó theo ràng buộc ở tiêu chí 6.
8. WHEN Planner_Agent ghi một `MealPlanPayload`, THE Planner_Agent SHALL bảo đảm `|total_calories - sum(components[i].calories)| ≤ 1.0` (kcal) và `len(components) ≥ 1`.
9. WHEN Planner_Agent gọi `suggest_dish` cho `day_index = d` của một plan, THE Planner_Agent SHALL truyền `recent_dish_ids` là danh sách có độ dài tối đa 6, chứa các `dish.id` đã được chọn cho plan đó ở các lần gọi `suggest_dish` liền trước (sắp xếp theo thứ tự chọn từ cũ đến mới, áp dụng FIFO khi vượt 6 phần tử).
10. WHEN Planner_Agent hoàn tất tạo plan thành công, THE Planner_Agent SHALL ghi đúng một row vào bảng `plans` với `status = 'active'`, `daily_kcal_target > 0`, `daily_protein_target` không null và `daily_protein_target > 0`.
11. IF bất kỳ tool con nào trong `{calculate_tdee, create_plan, suggest_dish, suggest_workout, append_plan_items}` trả `ToolResult(ok = false)` trong quá trình tạo plan, THEN THE Planner_Agent SHALL hủy quá trình tạo plan, SHALL NOT để lại row trong bảng `plans` với `status = 'active'` thuộc lần tạo đó, SHALL NOT để lại `plan_items` mồ côi, và SHALL trả về `error_code` phản ánh tool đã thất bại cho Agent_Orchestrator.
12. IF `UserProfile` thiếu bất kỳ trường nào trong `{age, gender, height_cm, weight_kg, activity_level, health_goal}` hoặc có giá trị nằm ngoài miền hợp lệ định nghĩa ở §6.1 (`age ∈ [10, 120]`, `height_cm ∈ [100, 250]`, `weight_kg ∈ [30, 300]`), THEN THE Planner_Agent SHALL từ chối tạo plan và trả `error_code = "INVALID_PROFILE"`.

### Requirement 4: Chất lượng gợi ý món ăn và bài tập

**User Story:** Là người dùng, tôi muốn các gợi ý món ăn và bài tập có macro hợp lý so với mục tiêu calo và đa dạng, để có thể áp dụng được trong thực tế mà không bị lặp một vài món/bài tập duy nhất.

#### Acceptance Criteria

1. WHEN `suggest_dish` được gọi với `target_kcal > 0`, THE Suggest_Dish_Tool SHALL trả về `Dish` có `0.7 * target_kcal ≤ dish.total_calories ≤ 1.5 * target_kcal` (sau khi scale `serving_grams`), và SHALL bảo đảm mọi `component.serving_grams ≥ 1`.
2. WHEN `suggest_workout` được gọi với `duration_min ∈ [10, 120]`, THE Suggest_Workout_Tool SHALL trả `WorkoutPlan` có `2 ≤ len(plan.exercises) ≤ 8` và `sum(ex.duration_minutes for ex in plan.exercises) ≤ duration_min`.
3. WHEN `suggest_dish` nhận `recent_dish_ids` không rỗng và tồn tại ít nhất một dish khác phù hợp với các ràng buộc khác, THE Suggest_Dish_Tool SHALL trả về dish có `id ∉ recent_dish_ids`.
4. WHERE `dietary_restrictions` chứa bất kỳ giá trị nào trong `{"vegetarian", "vegan", "low_carb", "high_protein", "no_seafood"}`, THE Suggest_Dish_Tool SHALL chỉ trả về `Dish` thỏa toàn bộ ràng buộc đó.
5. WHERE `equipment = "none"`, THE Suggest_Workout_Tool SHALL chỉ trả `exercises` có `ex.equipment` rỗng (bài tập tay không).
6. WHERE `user_state.fatigue_level ∈ {"high", "very_high"}`, THE Suggest_Workout_Tool SHALL hạ `level` một nấc theo thứ tự `advanced → intermediate → beginner` trước khi chọn bài tập.
7. WHEN `calculate_tdee` được gọi với một `UserProfile` hợp lệ (age, gender, height_cm, weight_kg, activity_level, health_goal trong miền hợp lệ §6.1), THE Calculate_TDEE_Tool SHALL trả về `{bmr, tdee, daily_kcal}` với `daily_kcal` được điều chỉnh theo `activity_level` và `health_goal`.
8. WHEN `search_food_nutrition` được gọi với một `query` non-empty, THE Server_Side_Tool SHALL trả về danh sách `Food` lấy từ `data/vietnamese_foods.json` cộng với top-k chunk RAG có liên quan, sắp xếp theo độ phù hợp.

### Requirement 5: Long-term memory hội thoại

**User Story:** Là người dùng có hội thoại kéo dài qua nhiều phiên, tôi muốn chatbot nhớ ngữ cảnh, các sở thích/dị ứng/mục tiêu của tôi, và truy xuất kiến thức nền liên quan đến câu hỏi, để không phải lặp lại thông tin mỗi lần.

#### Acceptance Criteria

1. THE Memory_Service SHALL chỉ thực hiện thao tác append vào `chat_messages`; FOR ALL row đã tồn tại trong `chat_messages`, các trường `id`, `content`, `role`, `created_at` SHALL bất biến trước và sau mỗi lần gọi `handleChatMessage`.
2. WHEN tổng số turn của một session vượt `SUMMARY_THRESHOLD`, THE Memory_Service SHALL cập nhật `chat_session_memory.rolling_summary` để cô đặc các turn cũ (giữ nguyên `KEEP_RAW_TURNS` turn cuối).
3. WHEN LLM đề xuất một fact mới về user (sở thích, dị ứng, mục tiêu, ràng buộc) trong quá trình hội thoại, THE Memory_Service SHALL lưu fact đó vào bảng `user_facts` với `status = 'pending'` và `source_msg_id` trỏ về message nguồn.
4. WHILE `user_facts.status = 'pending'`, THE Agent_Orchestrator SHALL hỏi user xác nhận trước khi đưa fact vào System_Prompt; chỉ fact có `status = 'confirmed'` mới được sử dụng để build prompt.
5. WHEN một câu hỏi mới đến, THE Memory_Service SHALL load và đưa vào System_Prompt: N turn raw gần nhất, `rolling_summary`, `user_facts` có `status = 'confirmed'`, và top-k chunk RAG có `similarity ≥ RAG_SIMILARITY_THRESHOLD`.
6. WHEN `query_rag` được gọi với `(query, top_k)` và `query` non-empty, THE RAG_Service SHALL trả về danh sách có `len(result) ≤ top_k`, mọi `chunk.similarity ≥ RAG_SIMILARITY_THRESHOLD`, và sắp xếp giảm dần theo `similarity`.
7. WHEN WebSocket reconnect sau disconnect, THE Memory_Service SHALL load lại lịch sử hội thoại từ DB và `session_id` SHALL giữ nguyên (không tạo session mới).
8. IF `chunk_embeddings` không có row nào, THEN THE RAG_Service SHALL trả về danh sách rỗng `[]`.

### Requirement 6: Giao thức WebSocket và bảo mật

**User Story:** Là người vận hành hệ thống, tôi muốn giao thức WebSocket có message format rõ ràng, có authentication và xử lý lỗi gọn gàng, để tránh lỗi protocol mơ hồ và chống truy cập trái phép.

#### Acceptance Criteria

1. WHEN một WebSocket connection được mở, THE Chat_Gateway SHALL liên kết duy nhất một `session_id` với connection đó và SHALL NOT cho phép multiplex nhiều `session_id` trên cùng một connection.
2. WHEN Chat_Gateway nhận message từ client, THE Chat_Gateway SHALL chỉ chấp nhận `type ∈ {"chat_message", "tool_result"}`.
3. WHEN Chat_Gateway gửi message về client, THE Chat_Gateway SHALL chỉ phát `type ∈ {"token", "tool_call", "done", "error"}`.
4. IF client gửi message không phải JSON hợp lệ hoặc thiếu trường required, THEN THE Chat_Gateway SHALL gửi `error` với `code = "BAD_MESSAGE"` và SHALL NOT đóng socket.
5. WHEN một WebSocket connection được khởi tạo, THE Chat_Gateway SHALL xác thực JWT token (truyền qua query param hoặc message đầu tiên) trước khi `accept`; IF token không hợp lệ, THEN THE Chat_Gateway SHALL đóng socket với close code `4401`.
6. WHEN ghi log production, THE Backend SHALL mask các trường PII liên quan tới sức khỏe (`weight_kg`, `height_cm`, `health_goal`, nội dung message thô) trước khi ghi vào file log.
7. IF nội dung trả về của một `tool_result` chứa "instruction-like content" (ví dụ chuỗi "ignore previous instructions"), THEN THE System_Prompt SHALL chứa hướng dẫn yêu cầu LLM coi nội dung tool_result là dữ liệu untrusted và SHALL NOT cho phép tool_result override System_Prompt.
8. WHEN Chat_Gateway đóng connection, THE Chat_Gateway SHALL dọn sạch toàn bộ `pendingCalls` của `session_id` đó để Tool_Dispatcher có thể reject các future tương ứng.

### Requirement 7: Migration code cũ sang kiến trúc Agent mới

**User Story:** Là người bảo trì backend, tôi muốn code mới thay thế hoàn toàn các module rời rạc cũ và áp dụng đúng các thay đổi schema, để hệ thống dễ debug, mở rộng và không còn dead code.

#### Acceptance Criteria

1. WHEN deploy code mới, THE Backend SHALL không còn import hoặc gọi các module: `services/intent_classifier.py`, `services/conversation_flow.py`, `services/prompt_builder.py`, `services/ai_analyzer.py`, `services/response_parser.py`, `services/user_state.py`, `services/dish_optimizer.py`, `services/meal_optimizer.py`, `services/exercise_optimizer.py`, `services/wger_search.py`, `services/wger_service.py`, `services/ingredient_translator.py`, `services/tdee_calculator.py`, `services/llm_service.py`, `routers/chat.py` (phiên bản cũ).
2. THE Backend SHALL giữ nguyên các data asset: `data/vietnamese_dishes.json`, `data/vietnamese_foods.json`, `data/wger_exercises_raw.json`, `data/exercises.json`, `data/nutrition.json`.
3. THE Backend SHALL giữ và mở rộng (không drop) hạ tầng: `db/init.sql`, `db/database.py`, `db/session_store.py`, các bảng `chat_sessions`, `chat_messages`, `plans`, `plan_items`, `knowledge_chunks`, `chunk_embeddings`, `wger_exercises`, `wger_ingredients`.
4. WHEN refactor `routers/plans.py`, THE Backend SHALL gọi `Tools.create_plan` và `Tools.append_plan_items` thay cho việc lưu `plan_items` với payload stub `'{"focus":"balanced"}'`.
5. WHEN Database_Migration được áp dụng, THE Database_Migration SHALL thêm các thay đổi sau theo `design.md` §10: bổ sung cột `tool_call_id`, `tool_name` vào `chat_messages`; cập nhật constraint `chat_messages_role_check` để chấp nhận `'tool'`; tạo các bảng `chat_session_memory`, `user_facts`, `tool_invocations`; thêm cột `daily_protein_target` vào `plans`; tạo unique index `tool_invocations_corr_idx (session_id, correlation_id)`.
6. WHEN backend khởi động, THE Backend SHALL khởi tạo `AgentOrchestrator` với tham số `max_steps = 6`, `tool_timeout_ms = 15000`, `LLMClient(model = "qwen2.5:7b-instruct")`, `ToolRegistry` đã đăng ký toàn bộ tool ở Requirement 2, `MemoryService`, `SessionStore`.
7. IF model LLM mặc định không hỗ trợ function calling đáng tin cậy ở một response cụ thể, THEN THE LLM_Client SHALL fallback sang JSON-mode bằng cách parse một block `<tool_call>{...}</tool_call>` cuối cùng trong output text.
8. WHEN backend reload `data/vietnamese_dishes.json` hoặc `data/wger_exercises_raw.json`, THE Backend SHALL load file một lần lúc startup và giữ in-memory; SHALL NOT reload mỗi request.

### Requirement 8: Trải nghiệm hội thoại tiếng Việt tự nhiên trên data thật

**User Story:** Là người dùng nói tiếng Việt, tôi muốn chatbot trả lời tự nhiên dựa trên dữ liệu thật của tôi và nhận diện đúng các yêu cầu phổ biến (xem nhật ký, ghi nhật ký, tạo kế hoạch), để cảm thấy đang đối thoại với một trợ lý hiểu mình.

#### Acceptance Criteria

1. WHEN user gửi câu hỏi tiếng Việt về dữ liệu cá nhân theo ngày (ví dụ "hôm qua tôi ăn gì có đủ protein không?"), THE Agent_Orchestrator SHALL gọi tool đọc dữ liệu phù hợp (`get_meal_log_range` hoặc `get_today_meals`) và SHALL trả lời chỉ dựa trên kết quả tool đó (không bịa số liệu không có trong tool_result).
2. WHEN user yêu cầu "tạo kế hoạch [goal] [N] tuần" với `N ∈ [1, 17]`, THE Agent_Orchestrator SHALL khởi động Planner_Agent với `duration_days = N * 7` và `goal` ánh xạ tương ứng (ví dụ "giảm cân" → `lose_weight`).
3. WHEN user yêu cầu "ghi lại [meal_type] hôm nay là [dish_name] [kcal] kcal", THE Agent_Orchestrator SHALL phát `tool_call: log_meal` với `arguments` đầy đủ và SHALL gửi câu xác nhận sau khi nhận `tool_result(ok=true)`.
4. WHEN streaming response trên LLM hợp lệ, THE Chat_Gateway SHALL gửi token đầu tiên trong ≤ 1500 ms kể từ thời điểm nhận `chat_message` (đo trên Ollama đã pre-warm).
5. WHEN turn kết thúc, THE Chat_Gateway SHALL gửi đúng một message `done` chứa `full_response` và `performed_actions` (danh sách `{tool, args, result_summary}` của các tool đã chạy).
6. WHEN user nhập một câu không khớp tool nào, THE Agent_Orchestrator SHALL trả lời text-only (LLM kết thúc với `tool_calls` rỗng), không gọi tool ép buộc.

