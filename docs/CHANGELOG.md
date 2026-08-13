## [2026-08-09] — LM Studio Local LLM Integration & Fast/Reasoning Modes
- **Changed:** Cấu hình hệ thống sử dụng mô hình ngôn ngữ lớn chạy cục bộ (Local LLM) qua LM Studio.
  - Cập nhật [apps/backend/.env](file:///c:/Project/Chatbot/apps/backend/.env) để sử dụng `OPENAI_BASE_URL=http://localhost:1234/v1` và đặt tên mô hình `LLM_MODEL` và `HEAVY_LLM_MODEL` là `qwen/qwen3-8b` (đã được nạp và hoạt động trong LM Studio).
  - Cập nhật [.env](file:///c:/Project/Chatbot/.env) ở thư mục gốc thành `OPENAI_BASE_URL=http://host.docker.internal:1234/v1` để tương thích với môi trường Docker Compose.
- **Added:** Tích hợp tính năng tự động chuyển đổi thông minh giữa **Fast Mode** (Thinking OFF) và **Reasoning Mode** (Thinking ON) dựa trên độ phức tạp của câu hỏi (phân loại qua [turn_router.py](file:///c:/Project/Chatbot/apps/backend/services/agent/turn_router.py)):
  - **Fast Mode (Thinking OFF):** Sử dụng kỹ thuật **Response Prefilling** (gửi tin nhắn mở đầu của assistant dưới dạng một dấu cách `" "`) để ép mô hình Qwen3/R1 bỏ qua quá trình suy nghĩ dài dòng khi xử lý các câu hỏi đơn giản (tra cứu calo, định nghĩa dinh dưỡng, chào hỏi). Giúp phản hồi cực kỳ nhanh chóng.
  - **XML Tool Call Fallback:** Khi chạy Fast Mode, bổ sung chỉ dẫn hệ thống yêu cầu mô hình xuất lệnh gọi tool dưới dạng JSON bọc trong thẻ `<tool_call>...</tool_call>` để tương thích với bộ phân tích cú pháp của hệ thống, giúp gọi tool (ghi chép nhật ký, gợi ý thực đơn) vẫn hoạt động 100% chính xác mà không cần qua bước suy nghĩ.
  - **Tối ưu trải nghiệm trực quan:** Tự động ẩn trạng thái "Đang suy nghĩ câu trả lời..." trên giao diện chat khi ở chế độ Fast Mode để tạo cảm giác phản hồi tức thì.
  - **Reasoning Mode (Thinking ON):** Giữ nguyên hành vi suy nghĩ sâu (Chain-of-Thought) cho các tác vụ phức tạp (lên thực đơn 7 ngày, tính macro dinh dưỡng nâng cao, phân tích RAG chéo).
- **Fixed:** Khắc phục mâu thuẫn trong gợi ý bài tập và tính toán calo tiêu thụ:
  - Cập nhật quy định chặt chẽ và bổ sung ví dụ Few-Shot vào [system_prompt.py](file:///c:/Project/Chatbot/apps/backend/services/agent/system_prompt.py) để bắt buộc mô hình phải gọi `suggest_workout` khi người dùng yêu cầu gợi ý bài tập (ví dụ: "tập tay"), cấm tuyệt đối việc tự nghĩ ra tên bài tập hay tự hướng dẫn bằng chữ.
  - Xóa bỏ việc mô hình tự phát ngôn sai lệch rằng "tập kháng lực/tập tay không tính calo đốt", làm rõ quy định calo hệ thống (sức bền/tạ tính 5 kcal/phút, cardio tính 8 kcal/phút).
  - Hướng dẫn mô hình map chính xác tiêu đề buổi tập được đề xuất từ tool (ví dụ: `Arms workout (beginner)`) vào lệnh gọi `log_exercise` thay vì ghi nhận chung chung là "tập tay" khi lưu kế hoạch gợi ý.
  - Cập nhật công cụ `log_exercise` trong [__init__.py](file:///c:/Project/Chatbot/apps/backend/services/agent/tools/__init__.py) hỗ trợ truyền tham số mô tả `description` chứa danh sách chi tiết các động tác được gợi ý.
  - Cập nhật [ai_chat_provider.dart](file:///c:/Project/Chatbot/apps/mobile/lib/providers/ai_chat_provider.dart) và [detail_bottom_sheet.dart](file:///c:/Project/Chatbot/apps/mobile/lib/widgets/detail_bottom_sheet.dart) trên app Flutter để tự động hiển thị danh sách các động tác con được mô tả từ `description`, đồng thời nhận diện chuỗi bài tập kết hợp để hiển thị thông báo phù hợp (*'Đây là chuỗi bài tập kết hợp. Chi tiết thông tin được cung cấp bởi AI.'*) thay vì hiển thị cảnh báo lỗi/bịa bài tập (*'Bài tập này chưa có trong cơ sở dữ liệu wger...'*).
  - Khắc phục lỗi mất thẻ bài tập/dinh dưỡng trực quan (Structured Card) khi tải lại lịch sử hội thoại: Nâng cấp hàm `loadExistingSession` trong [ai_chat_provider.dart](file:///c:/Project/Chatbot/apps/mobile/lib/providers/ai_chat_provider.dart) để tự động phân tích nội dung văn bản của tin nhắn xác nhận từ quá khứ nhằm tái tạo lại cấu trúc thẻ; đồng thời cập nhật [chatbot_screen.dart](file:///c:/Project/Chatbot/apps/mobile/lib/features/chat/screens/chatbot_screen.dart) để tự động ẩn nút "Lưu vào nhật ký" trùng lặp trên các thẻ bài tập/dinh dưỡng đã được lưu thành công trong lịch sử.
  - Loại bỏ việc lưu trữ tin nhắn lỗi (`LLM_UNAVAILABLE` hoặc `LLM_ERROR`) vào database khi LLM gặp sự cố: Cập nhật cơ chế xử lý lỗi trong [orchestrator.py](file:///c:/Project/Chatbot/apps/backend/services/agent/orchestrator.py) để re-raise các lỗi ngoại lệ kết nối/phản hồi lỗi, kích hoạt rollback giao dịch tự động của router để không lưu trữ cả tin nhắn của người dùng lẫn tin nhắn lỗi của hệ thống khi không có câu trả lời thực tế thành công.
- **Verified:** Chạy thử nghiệm thành công trên LM Studio và vượt qua toàn bộ **423/423 bài kiểm thử unit tests** của backend.

## [2026-08-06]
- **Changed:** **Tái cấu trúc cây thư mục theo chuẩn monorepo.** Phẳng hoá `Chatbot/NCKH/` → `Chatbot/` (bỏ 1 tầng lồng thừa); `HealthApp/health_app/` → `apps/mobile/`; `HealthApp/ai_backend/backend/` → `apps/backend/` (bỏ 2 tầng lồng thừa). Thư mục `HealthApp/` bị loại bỏ hoàn toàn.
- **Changed:** `Dataset/` tách thành `data/raw/` (CSV, JSON, PDF nguồn) và `data/scripts/` (script parse/convert). Đổi tên `Cook book Vietnamese of Twin cooker_final.pdf` → `cookbook_vietnamese_twin_cooker.pdf` (bỏ khoảng trắng trong tên file).
- **Changed:** Sắp xếp lại `docs/` thành `architecture/`, `features/`, `guides/`, `archive/`, `thesis/`. Gộp tài liệu backend rải rác (`QUICK_START.md`, `GPU_SETUP.md`, `PGVECTOR_GUIDE.md`, `DOCKER_README.md`, `setup_firebase_guide.md`) vào `docs/guides/`; chuyển nhật ký task đã hoàn thành vào `docs/archive/`.
- **Fixed:** Xoá `HealthApp/.gitignore` — đây là `.gitignore` của **repo Flutter SDK** bị đặt nhầm, không liên quan tới ứng dụng. Xoá `HealthApp/.gitattributes` và `HealthApp/.vscode/settings.json` trùng lặp với bản ở gốc.
- **Fixed:** Gộp 3 bản `pyrightconfig.json` trùng lặp (gốc workspace, `NCKH/`, `backend/`) còn 1 bản ở gốc trỏ đúng `apps/backend`. Cập nhật `.vscode/settings.json` với interpreter, pytest args và `dart.flutterSdkPath`.
- **Fixed:** Gộp 2 bản `AGENTS.md` trùng lặp, giữ bản superset (có mục "ZERO-REPEAT DEFECT MANDATE"), lưu UTF-8 không BOM.
- **Security:** Gỡ `firebase_options.dart` (chứa API keys) khỏi git index bằng `git rm --cached` — file vẫn còn trên đĩa và đã có rule trong `.gitignore`. Chỉ `firebase_options.dart.example` được track.
- **Fixed:** Cập nhật đường dẫn theo cấu trúc mới trong `docker-compose.yml`, `start-all.bat`, và các script Python (`convert_vn_foods.py`, `fix_uw.py`, `parse_pdf_full.py`, `parse_dinhduong.py`, `convert_to_dart.py`) — thay đường dẫn tương đối dễ vỡ bằng `Path(__file__).resolve().parents[n]`.
- **Fixed:** Xoá `analysis_options.yaml` ở gốc (loại trừ `flutter/**` không còn tồn tại); `apps/mobile` đã có bản riêng. Bỏ thuộc tính `version` lỗi thời trong `docker-compose.yml`.
- **Changed:** Thêm `/rules/` và `/.continue/` (config riêng của từng AI IDE) vào `.gitignore`.
- **Verified:** `flutter analyze` 22 info / 0 error, `flutter test` 23/23 passed, `flutter build web` thành công, `pytest` backend **399/399 passed**, `docker compose config` hợp lệ.

## [2026-08-06] — Môi trường Flutter
- **Changed:** Flutter SDK 3.44.8 (Dart 3.12.2) được cài đặt ngoài workspace tại `C:\flutter` và thêm `C:\flutter\bin` vào biến môi trường `PATH` hệ thống. Toàn bộ tài liệu chuyển từ đường dẫn tương đối (`..\..\flutter\bin\flutter.bat`, `../../../flutter/bin/...`) sang gọi lệnh `flutter` / `dart` trực tiếp.
- **Changed:** Cập nhật đường dẫn thư mục dự án trong `docs/RUN_GUIDE_LDPLAYER.md` và `docs/05_run_guide.md` từ `C:\Users\ADMIN\Downloads\Project\Chatbot-NCKH\NCKH\NCKH` sang `C:\Project\Chatbot`; thay các link `file:///` tuyệt đối bằng đường dẫn tương đối trong `docs/04_troubleshooting.md`.
- **Added:** Bổ sung mục "Môi Trường Đã Xác Minh" và "Lệnh Kiểm Thử" vào `docs/05_run_guide.md`, ghi nhận kết quả: `flutter pub get` OK, `flutter analyze` 22 info / 0 error / 0 warning, `flutter test` 23/23 passed, `flutter build web --release --no-tree-shake-icons` thành công.
- **Changed:** Ghi chú máy phát triển chưa cài Chrome — tài liệu chuyển sang dùng device `edge` hoặc `web-server` cho Flutter Web; Visual Studio C++ chưa cài nên chưa build được Windows desktop; Android SDK 36.0.0 cần chạy `flutter doctor --android-licenses`.
- **Changed:** Cập nhật `HUONG_DAN_CAI_DAT.md` bỏ tham chiếu `setup.bat` / `run.bat` (không tồn tại trong `health_app`) và thư mục SDK nhúng `flutter/`.

## [2026-08-01]
- **Added:** Thiết lập bộ unit test đánh giá khả năng tự học thích ứng (Adaptive Learning Evaluation) của AI tại [test_adaptive_learning.py](../apps/backend/tests/test_adaptive_learning.py) gồm 6 ca kiểm thử chi tiết hóa dưới dạng Ma trận chuyển đổi trạng thái (State Transition Matrix).
- **Added:** Thiết lập bộ unit test an toàn sức khỏe y tế mở rộng tại [test_health_safety_eval.py](../apps/backend/tests/test_health_safety_eval.py) kiểm thử các tình huống gợi ý món ăn nâng cao (tìm kiếm có dấu/không dấu, bộ lọc không hải sản, món chay), mâu thuẫn ràng buộc cực đoan, ánh xạ lỗi và tuân thủ ranh giới y tế trong system prompt.
- **Fixed:** Khắc phục lỗi chatbot gợi ý món ăn không đúng ý đồ người dùng (ví dụ: gợi ý Mì xào hải sản khi được yêu cầu Cơm) bằng cách bổ sung tham số tìm kiếm `query` tùy chọn vào schema và hàm xử lý của công cụ gợi ý món ăn `suggest_dish` cùng thuật toán so khớp không dấu tiếng Việt `_remove_accents`.
- **Added:** Tích hợp tính năng hiển thị quá trình suy nghĩ thời gian thực (Real-time Thinking Process). Hỗ trợ tách biệt và stream tokens suy nghĩ (`reasoning_content` của DeepSeek / thẻ `<think>...</think>`) cùng các thông báo trạng thái xử lý trung gian (`send_status` như RAG query, tool call execution) lên giao diện người dùng.
- **Added:** Thiết kế widget `AIThoughtsPanel` collapsible (có thể thu gọn/mở rộng với hiệu ứng) trên Flutter để hiển thị nội dung suy nghĩ của chatbot một cách chuyên nghiệp.
- **Fixed:** Khắc phục lỗi chatbot trả lời hành động ảo (khẳng định đã ghi món/bài tập nhưng không gọi tool) bằng cách cập nhật quy tắc `_TOOL_RULES` và thêm ví dụ Few-Shot chi tiết về gọi công cụ (`tool_calls`) cho các trường hợp người dùng đồng ý/xác nhận lưu gợi ý thực đơn/bài tập vào `system_prompt.py`.
- **Fixed:** Ẩn hoàn toàn nút "Lưu vào nhật ký" thừa thãi và tối ưu chiều rộng nút "Xem chi tiết" trên các thẻ gợi ý món ăn/bài tập có cấu trúc khi chatbot đã tự động lưu thành công các món/bài tập này.
- **Fixed:** Thay thế các biểu tượng Material Icons dạng Rounded/Outline Rounded và các icon không được hỗ trợ trên bản build Web bằng các phiên bản tiêu chuẩn ổn định hơn (Icons.person, Icons.person_outlined, Icons.monitor_weight, Icons.height, Icons.analytics, Icons.local_fire_department, Icons.bolt, Icons.directions_run, Icons.dashboard, Icons.flag, Icons.logout, Icons.edit, Icons.smart_toy...), giải quyết triệt để vấn đề mất icon và đồng bộ hóa hiển thị trên tab bar của giao diện Web.
- **Fixed:** Chỉ tạo cuộc hội thoại trong cơ sở dữ liệu khi người dùng gửi tin nhắn trò chuyện đầu tiên thay vì tạo cuộc hội thoại trống ngay khi kết nối WebSocket bằng cách trì hoãn lệnh gọi `_ensure_session_exists` từ hàm `authenticate()` sang phần nhận tin nhắn của `chat_gateway.py`.
- **Added:** Upgraded chatbot memory architecture to support **Adaptive Memory State Updates** (`add`, `update`, `remove` actions) to automatically deactivate conflicting or outdated user facts, preventing prompt pollution and conflicting instructions.
- **Added:** Implemented **Contextual Window Memory Retrieval** using PostgreSQL full-text search combined with window functions (`ROW_NUMBER()`) to pull matching dialogue snippets along with their surrounding 2 preceding and 2 succeeding turns, merging overlapping exchanges automatically.
- **Fixed:** Prevented irrelevant RAG vector database queries on short conversational responses (e.g. "có", "không", "ừ", "ok") by expanding the `is_simple_greeting_or_chitchat` helper in `memory_service.py` to match short affirmative/negative responses, resolving chatbot prompt confusion.
- **Fixed:** Resolved FastAPI type checking errors in `memory_service.py` by casting row values to correct schemas (`FactCategoryLiteral`, `FactStatusLiteral`, `ChatRoleLiteral`).
- **Fixed:** Eliminated Python 3.12+ deprecation warnings by replacing `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)` in `memory_service.py` and `session_store.py`.
- **Fixed:** Removed unused import `app_theme.dart` in `account_settings_screen.dart` to resolve Flutter analyzer warning.
- **Added:** Created Flutter Web Mobile Simulator layout (`_WebPhoneWrapper` in `main.dart`) to constrain the app within a realistic smartphone frame on desktop browsers with switchable aspect ratios (16:9, 19.5:9, 21:9) and themes (Midnight Black, Neon Glow, Glassmorphic).
- **Added:** Added detailed startup instructions to `docs/05_run_guide.md` for both automated and manual service startup.

## [2026-07-29]
- **Fixed:** Resolved browser font blocking issues by creating a custom python server `serve_web.py` to correctly map `.otf` and `.ttf` files to `font/otf` and `font/ttf` MIME types instead of `application/octet-stream` causing missing icons.
- **Fixed:** Resolved `Null check operator used on a null value` runtime crash in `FormattedMarkdownText` by safe-unpacking regex match groups using null-coalescing fallback operators (`?? ''`).
- **Fixed:** Fixed missing filled icons (e.g., `Icons.person_rounded` on active BottomNavigationBar, and badges like `Icons.health_and_safety_rounded`, `Icons.smart_toy_rounded`, `Icons.directions_run_rounded` on `AccountSettingsScreen`) on Flutter Web by building the web app with `--no-tree-shake-icons`.
- **Added:** Implemented complete 2-way data synchronization between AI Chatbot and Flutter HealthApp (`get_active_plan`, `mark_plan_item_complete`, `get_weight_history`, `log_*`).
- **Added:** Integrated `getActivePlanDetail` in `BackendApiService` and connected active plan retrieval with FastAPI backend PostgreSQL database.
- **Added:** Floating AI Assistant (FAB) enabled across all 5 navigation screens with draggable bottom sheet chat interface.
- **Added:** AI Health Nudge Card on Dashboard screen with real-time missing indicator checks (hydration, missing meals, exercise).
- **Added:** Structured documentation system in `docs/` (`01_architecture.md`, `02_database_schema.md`, `03_features/chatbot_integration.md`, `04_troubleshooting.md`).
- **Fixed:** Resolved `ChatbotScreen.initState()` overwriting provider references by passing all 4 providers (`Exercise`, `Nutrition`, `Lifestyle`, `Health`) to `AIChatProvider.setProviders()`.
- **Fixed:** Added null-safe checks in `AIChatProvider.setProviders()` to prevent resetting existing provider references when optional arguments are omitted.
- **Fixed:** Resolved `get_active_plan` returning empty mock data by querying backend endpoints with 404 safety fallback.
- **Fixed:** Fixed null safety dereference in `proactive_checkin_card.dart` and aligned water intake getter to `todayWaterIntake`.
- **Optimized:** Implemented mandatory Parallel Tool Calling prompt directive in `system_prompt.py` forcing LLM to dispatch all context tools in a single turn.
- **Optimized:** Reduced `max_agent_steps` from 6 to 3 and `tool_timeout_ms` from 15000 to 5000 in `config.py`.
- **Optimized:** Applied 1.0-second `asyncio.wait_for` timeout for `queryRag` vector searches in `memory_service.py` to prevent vector embeddings from delaying response generation.
- **Fixed:** Applied Ultra High Contrast typography across `AccountSettingsScreen`: pure white/sky-blue text on dark slate profile cards (`#0F172A`), deep dark slate titles (`#0F172A`), and bold black values (`#0F172A`) on tinted biometric cards (`#1D4ED8`, `#047857`, `#C2410C`).
- **Added:** Added HealthApp Brand Logo badges across the Settings screen header, profile avatar notch, goal/activity item boxes, and app brand footer.
- **Lessons Learned (Anti-Repetition):** Always pass all active providers to `setProviders()` in screen initializers, enforce parallel tool execution via system prompt rules, and place strict timeouts on RAG embeddings searches.

## [2026-07-25]
- **Added:** Implemented **3-Module Modular Architecture** (Module 1: Dinh dưỡng, Module 2: Thể chất, Module 3: Sức khỏe Tinh thần & Lifestyle).
- **Added:** Created `lifestyle_model.dart`, `lifestyle_provider.dart`, and `lifestyle_screen.dart` for Module 3 management in Flutter.
- **Added:** Registered client tools `get_lifestyle_logs`, `log_lifestyle`, `set_lifestyle_reminder` in FastAPI backend `tools/__init__.py` and mapped domain modules via `DOMAIN_MODULE_MAP`.
- **Added:** Updated `system_prompt.py` to instruct LLM on modular domain routing and lifestyle tool invocation strategies.
- **Added:** Created scientific research design document `docs/MODULAR_ARCHITECTURE_DESIGN.md` for NCKH paper publishing.
- **Fixed:** Fixed parameter structure mismatch in `wger_food_search_widget.dart` by properly nesting `MealItem` within `MealModel.items`.
- **Lessons Learned (Anti-Repetition):** Always construct domain models (e.g. `MealModel`) with their exact expected parameters (`items: [MealItem]`) rather than passing raw item properties directly to top-level model constructors.

## [2026-06-30]
- **Added:** Real-time token streaming to Flutter UI (word-by-word rendering).
- **Added:** Locked input TextField and disabled send button when AI chatbot is streaming responses.
- **Added:** Optimistic UI updates for `log_meal` and `log_exercise` client-side tool calls in Flutter.
- **Added:** Local keyword-based nutrition macro lookup inside client `ActionItem` models.
- **Added:** Bún Riêu to backend `nutrition.json` dataset and re-loaded into PostgreSQL vector database (RAG).
- **Added:** Compound recipe splitting in frontend `wger_models.dart` and `ai_chat_provider.dart` to automatically expand compound dishes (such as Bún riêu, Phở bò, Phở gà, Bún chả, Bánh mì kẹp, Cơm tấm) into constituent ingredients for accurate local macro calculations.
- **Optimized:** Truncated context history window to 6 turns in the orchestrator to decrease LLM response latency.
- **Optimized:** Stripped `calories` and `calories_burned` calculation requirements from LLM system prompts and tool schemas.
- **Fixed:** Chatbot message bubble displays stream content on token arrival instead of hiding it in the thinking indicator.
- **Fixed:** Public accessibility of `lookupFoodNutrition` static helper across Dart libraries.
- **Fixed:** Resolved `InterfaceError: another operation is in progress` database crash by removing redundant concurrent `commit()` calls from the WebSocket `tool_result` event handler.
- **Lessons Learned (Anti-Repetition):** Ensure that `notifyListeners()` is triggered on real-time stream token updates to notify widgets. Avoid library-private prefixes (`_`) for static model helpers that need to be accessed by providers across library boundaries. Do not run database commits (`commit()`) concurrently on a single shared async SQLAlchemy session when other asynchronous tasks are actively executing queries/updates.
## [2026-06-25]
- **Added:** System Prompt instructions for generating `StructuredResponse` JSON to enable Flutter action cards (Food/Exercise UI).
- **Added:** System Prompt rules enforcing strict Medical Decorum (no diagnosis).
- **Added:** Backend `orchestrator.py` now parses `{"type": "structured", ...}` JSON from LLM's text stream and routes it via WebSocket.
- **Fixed (AI Hallucination):** The AI fabricated an excuse ("hệ thống hồ sơ đang tạm thời không phản hồi") to ask the user for profile data manually when asked to create a plan. The system prompt was updated to aggressively enforce calling `get_user_profile` for ALL tasks and strictly forbade it from making excuses or asking the user for profile data.
- **Lessons Learned (Anti-Repetition):** Always check if the application is running via Docker or natively. When running via Docker, verify if the files being edited are mounted via volumes or baked into the image. If baked in, a full `docker-compose up --build` is required. Also, for LLMs with strong chat instincts (like DeepSeek), ensure stream parsing handles late-arriving tool calls.
