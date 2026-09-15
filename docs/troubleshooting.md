# 04. Sổ Tay Sửa Lỗi (Troubleshooting Guide)

### 60. Lỗi đè FloatingActionButton (FAB) lên Bottom Dock & Khối đen pill trạng thái trong Plan Card

- **Triệu chứng (Symptoms):**
  1. Nút `+` (thêm bữa ăn) tại màn hình Dinh dưỡng bị đè trùng, che lấp lên Bottom Navigation Bar và bóng Chatbot FAB ở giữa.
  2. Huy hiệu trạng thái kế hoạch (`_Pill`) hiển thị thành một khối chữ nhật màu đen đặc, không đọc được chữ.
  3. Tiêu đề "Thực đơn theo kế hoạch" bị ngắt dòng chật chội và nội dung cuối danh sách bị che khuất bởi thanh điều hướng.
- **Nguyên nhân gốc (Root cause):**
  1. `NutritionScreen` nằm trong `IndexedStack` của `HomeScreen`, `FloatingActionButton` mặc định bám đáy Scaffold bên trong (`bottom: 0`), gây chồng chéo với Dock nổi 64px của `HomeScreen`.
  2. `_Pill` trong `versioned_plan_card.dart` sử dụng `Theme.of(context).colorScheme.primaryContainer` (màu Slate đậm trong theme) kết hợp `labelSmall` cùng tone màu gây mất tương phản (đen trên nền đen).
  3. `PlannedDayPlanSection` có tiêu đề dài đi kèm nút `IconButton` lớn trong cùng một `Row` cố định gây vỡ dòng trên màn hình hẹp.
- **Cách xử lý (Resolution):**
  1. Đẩy `FloatingActionButton` của `NutritionScreen` lên trên với `Padding(padding: EdgeInsets.only(bottom: 72))` và thêm nút `+` nhanh vào thanh AppBar.
  2. Tăng khoảng đệm cuộn cuối danh sách `padding: EdgeInsets.fromLTRB(16, 12, 16, 96)`.
  3. Cập nhật `_Pill` với màu nền mờ `color.withValues(alpha: 0.1)` và màu chữ `color` tương ứng theo từng trạng thái kế hoạch (`_statusColor(lifecycle)`).
  4. Tối ưu tiêu đề `PlannedDayPlanSection` với `Flexible` text, badge "Dự kiến" gọn gàng và nút chuyển "Xem chi tiết →" dạng pill.
- **Kiểm thử (Verification):** Chạy `flutter test` toàn bộ 131/131 bài test đều pass (`All tests passed!`).

### 59. Giao diện Kế hoạch (Plan V2) thiếu trực quan và xung đột nhiều Scrollable trong Widget Test

- **Triệu chứng (Symptoms):** Màn hình Kế hoạch đơn điệu, các ngày hiển thị dạng khối xám thô (`AppColors.background`), thiếu phân loại danh mục (Dinh dưỡng / Tập luyện / Sức khỏe), không có tab chuyển ngày linh hoạt trong chi tiết kế hoạch. Khi dùng `SingleChildScrollView` cho thanh tab trong danh sách gây lỗi `Too many elements` (`find.byType(Scrollable)`).
- **Nguyên nhân gốc (Root cause):**
  1. Thẻ kế hoạch (`_PlanOverviewCard`) và thẻ ngày (`_DayCard`) chưa áp dụng thiết kế Bento card chuẩn, thiếu badge phân loại macro (P/C/F) và format thứ/ngày rõ ràng.
  2. Việc nhúng `SingleChildScrollView(scrollDirection: Axis.horizontal)` bên trong `ListView` tạo ra nhiều `Scrollable`, làm vỡ `scrollUntilVisible` trong widget testing.
- **Cách xử lý (Resolution):**
  1. Thay thế `SingleChildScrollView` bằng `Wrap(spacing: 8, runSpacing: 8)` cho cả thanh bộ lọc thư viện kế hoạch và thanh chọn ngày trong chi tiết kế hoạch.
  2. Nâng cấp `_PlanLibraryHero`: Thêm thống kê số kế hoạch đang áp dụng, tổng mục dự kiến với gradient Slate cao cấp.
  3. Bổ sung `_MacroBadge` (P: Protein, C: Carbs, F: Fat) cho từng món ăn và thời lượng/hiệp tập cho bài tập.
  4. Nâng cấp `_PlanActions`: Phân cấp rõ ràng Primary CTA (Lưu, Kích hoạt), Secondary Outlined CTA (Chỉnh sửa), và Subtle Destructive (Hủy/Tạm dừng).
  5. Thêm thanh chọn ngày tương tác (`_buildDayTabs`) trong `PlanDetailScreen` cho phép xem tổng thể hoặc lọc theo từng ngày cụ thể.
- **Kiểm thử (Verification):** Chạy `flutter test` toàn bộ 131/131 bài test đều pass (`All tests passed!`).

### 58. Lỗi không cuộn được / kẹt kéo chuột trên Desktop & Web (Flutter Scroll Behavior & UI Overhaul)

- **Triệu chứng (Symptoms):** Người dùng sử dụng chuột hoặc trackpad kéo/cuộn danh sách trên Web/Desktop bị trơ, không cuộn được hoặc giật cục. Giao diện màu xám thô và hiệu ứng chuyển tab/loading còn cứng.
- **Nguyên nhân gốc (Root cause):**
  1. Flutter mặc định chỉ kích hoạt cử chỉ kéo (`dragDevices`) cho `PointerDeviceKind.touch` và `stylus`, bỏ qua `PointerDeviceKind.mouse`, `trackpad`, và `unknown`.
  2. Màu sắc và hiệu ứng shimmer loading dùng màu đen xám `grey[800]` thô cứng thay vì tone Bento `#E2E8F0` / `#F1F5F9`.
- **Cách xử lý (Resolution):**
  1. Thêm `AppScrollBehavior` kế thừa `MaterialScrollBehavior` cấu hình `dragDevices: {PointerDeviceKind.touch, PointerDeviceKind.mouse, PointerDeviceKind.trackpad, PointerDeviceKind.stylus, PointerDeviceKind.unknown}` và áp dụng `BouncingScrollPhysics(parent: AlwaysScrollableScrollPhysics())`.
  2. Gắn `scrollBehavior: const AppScrollBehavior()` vào `MaterialApp` tại `main.dart`.
  3. Chuẩn hóa hệ thống thiết kế Bento: Thẻ nền trắng `#FFFFFF`, viền mờ 1px `Colors.black.withValues(alpha: 0.04)`, ambient shadow mềm mại `AppShadows.card`, `InteractiveCard` với hiệu ứng nhấn nhún (spring scale bounce), và nút AI Chatbot FAB với breathing pulse animation.
- **Kiểm thử (Verification):** Chạy `flutter test` toàn bộ 131/131 unit & widget tests đều pass.

### 57. FastAPI Docker container starts but cannot serve port 8080

- **Symptoms:** `docker compose` reports the container as running, but
  `GET /health` closes the connection and `start-all.bat` never begins step
  4/4 (the Flutter static server).
- **Root cause:** The D4.1/E2/E3 modules derived the repository root with a
  fixed `Path.parents[index]`. Local source has `<repo>/apps/backend`, but the
  Docker development override mounts the backend directly at `/app`. The
  import of the workout planner then raised `IndexError` before FastAPI startup
  completed.
- **Resolution:** Derive `BACKEND_DIR` first and use the checkout root only
  when it is actually available; otherwise use the mounted backend directory.
  This preserves local Git provenance while container runtime imports do not
  depend on inaccessible parents.
- **Regression check:** Confirm `GET http://localhost:8080/health` returns
  `200` before starting the Flutter server. The 2026-08-31 smoke test verified
  the port-3000 web shell plus nutrition and Wger API responses.

## E4.1: Kế hoạch tập không tạo được hoặc không lưu được

- Nếu card trả `CLARIFICATION_REQUIRED`, kiểm tra `workout_profile` có mục tiêu, thời lượng, dụng cụ, pain status và safety screen rõ ràng. Các profile cũ được giữ unknown, không được tự gán mức novice/dụng cụ.
- Nếu legacy history không tải được từ Firestore server, E4 nhận `ERROR` thay vì cache. Người dùng có thể thử lại; đừng diễn giải là tuần này có 0 buổi.
- `WORKOUT_WRITE_MODE=off` là mặc định và mọi nút lưu/ghi kết quả sẽ trả `WORKOUT_WRITE_DISABLED`. Chỉ bật `explicit` sau khi API có ràng buộc user ID với principal đã xác thực.
- Kết quả E4 chỉ được ghi khi người dùng bấm hành động rõ ràng. Actual reps/load/RPE/RIR/pain để trống là unknown, không được lấy từ mục tiêu bài tập.

## D1: chatbot báo lưu bữa ăn nhưng consumed totals không đổi

- **Nguyên nhân gốc:** `log_meal` tạo `MealModel` với mặc định
  `isCompleted=false`, trong khi consumed totals chỉ cộng meal completed. Đồng
  thời `NutritionProvider.addMeal` nuốt lỗi Firestore, khiến caller không biết
  persistence thất bại.
- **Cách xử lý:** meal do chatbot ghi nhận là `CONSUMED` được tạo với
  `isCompleted=true`; document được đọc lại từ server để xác nhận. Nếu ghi/đọc
  xác nhận thất bại, optimistic state được rollback và write result là `ERROR`,
  nên chatbot không được phát thông báo “đã lưu”.
- **Hồi quy:** chạy `development_d1_state_correctness_test.dart`, gồm cả
  log → read → consumed total và synthetic failed persistence.

## 🛠️ Lỗi Thường Gặp & Cách Xử Lý

### 1. `get_active_plan` trả về null hoặc quăng exception
- **Nguyên nhân**: Bảng `plans` chưa có bản ghi active cho `user_id` hoặc backend endpoint `/plans/{user_id}/active` bị 404.
- **Cách xử lý**: Đã cập nhật `BackendApiService.getActivePlan` bắt 404 an toàn và trả về `null`. Khi AI gọi `get_active_plan`, `AIChatProvider` dùng `getActivePlanDetail` để tải dữ liệu hoàn chỉnh.

### 2. UI Flutter không cập nhật khi AI gọi `log_meal` / `log_exercise`
- **Nguyên nhân**: Dữ liệu đã ghi vào cache/DB nhưng provider giao diện chưa phát tín hiệu làm mới.
- **Cách xử lý**: Đảm bảo trong `AIChatProvider._handleToolCall`, sau khi gọi `addMeal` hoặc `addExercise` đều invoke `notifyListeners()`.

### 3. Missing parameter or Null dereference trong `proactive_checkin_card`
- **Nguyên nhân**: Trường `activeNudge` trả về `null` hoặc thuộc tính `todayWaterIntake` bị gọi sai tên (`todayWaterMl`).
- **Cách xử lý**: Đã bổ sung logic kiểm tra null-safe `nudge?['id']` và sử dụng getter chính xác `health.todayWaterIntake`.

### 4. WebSocket timeout hoặc connection error
- **Nguyên nhân**: Backend FastAPI chưa khởi động hoặc sai cổng (8080).
- **Cách xử lý**: Kiểm tra `AIChatbotConfig.wsUrl`. Đảm bảo backend được khởi chạy với `uvicorn main:app --port 8080`.

### 5. Provider Reference bị reset khi mở `ChatbotScreen`
- **Nguyên nhân**: Trong `ChatbotScreen.initState()`, hàm `aiChatProvider.setProviders(...)` chỉ được gọi với `exerciseProvider` và `nutritionProvider`, khiến `lifestyleProvider` và `healthProvider` bị set về `null`. Khi AI gọi các tool như `get_lifestyle_logs`, `log_lifestyle`, `get_weight_history`, `log_weight` thì bị đứt gãy.
- **Cách xử lý**: 
  1. Trong `ChatbotScreen.initState()`, truyền đầy đủ cả 4 Providers từ `context` vào `setProviders(...)`.
  2. Trong `AIChatProvider.setProviders()`, thêm kiểm tra `if (provider != null)` để không ghi đè giá trị `null` lên các provider reference sẵn có.

### 6. Lỗi `INTERNAL_ERROR - name 'asyncio' is not defined`
- **Nguyên nhân**: Thiếu `import asyncio` ở đầu file `memory_service.py` khi sử dụng `asyncio.wait_for` cho RAG Query.
- **Cách xử lý**: Đã thêm `import asyncio` vào `memory_service.py` và khởi động lại FastAPI backend server.

### 7. Lỗi Biểu Tượng Material Icons Bị Mất/Tẩy Trắng Trên Flutter Web Release
- **Nguyên nhân**: Khi thực hiện lệnh `flutter build web --release`, thuật toán Icon Tree-Shaking của Flutter mặc định cắt giảm phông chữ `MaterialIcons-Regular.otf`, dẫn đến các biểu tượng MaterialIcons bị mất hoặc biến thành các ô màu trống không có biểu tượng.
- **Cách xử lý**: Bổ sung cờ `--no-tree-shake-icons` vào câu lệnh biên dịch Flutter Web (`flutter build web --release --no-tree-shake-icons`) để giữ lại toàn bộ phông biểu tượng đầy đủ.

### 8. Lỗi Biểu tượng không hiển thị do MIME Type (BaseHTTP / Python http.server trên Windows)
- **Nguyên nhân**: Trình duyệt Chrome/Edge từ chối tải tệp font `.otf` hoặc `.ttf` vì Python `http.server` trả về `Content-type: application/octet-stream` (MIME không hợp lệ cho font, do Windows Registry thiếu cấu hình kiểu file).
- **Cách xử lý**: 
  1. Viết kịch bản khởi chạy [serve_web.py](../apps/mobile/serve_web.py) sử dụng `mimetypes.add_type` đăng ký kiểu MIME chuẩn `font/otf` cho `.otf` và `font/ttf` cho `.ttf`.
  2. Cấu hình [start-all.bat](../start-all.bat) chạy `serve_web.py` thay vì chạy mô-đun `-m http.server` mặc định.
### 9. Chatbot nói chuyện không liên quan / tự gợi ý món khác (như Cao lầu) khi người dùng trả lời "có"
- **Nguyên nhân**: Khi người dùng phản hồi ngắn gọn dạng khẳng định/phủ định (như "có", "không", "ừ", "ok"), turn router phân loại câu hỏi là `SIMPLE` để giữ các công cụ (tools) hoạt động. Tuy nhiên, `MemoryService.loadContext` không nhận diện các từ này là từ chitchat/hội thoại thông thường nên đã thực hiện truy vấn RAG qua Vector Database (pgvector) bằng các từ khóa này (ví dụ: tìm kiếm vector cho từ "có"). Điều này trả về các chunks kiến thức ngẫu nhiên không liên quan (như công thức Cao lầu) và nhét vào prompt, khiến LLM bị phân tâm khỏi ngữ cảnh trước đó.
- **Cách xử lý**: Cập nhật hàm `is_simple_greeting_or_chitchat` trong `memory_service.py` để làm sạch chuỗi và so khớp với danh sách mở rộng chứa các từ khóa hội thoại ngắn (affirmative: "có", "ừ", "vâng", "được"; negative: "không", "hủy", "thôi"). Khi đó, các câu trả lời ngắn này sẽ bỏ qua truy vấn RAG, giúp hội thoại liền mạch và LLM gọi đúng công cụ cần thiết (như `log_meal` cho món ăn đã gợi ý trước đó).

### 10. Chatbot trả lời hành động ảo, khẳng định đã ghi món ăn/bài tập vào nhật ký nhưng thực tế không gọi tool
- **Nguyên nhân**: Khi người dùng phản hồi đồng ý hoặc lựa chọn món ăn được gợi ý (ví dụ: "Canh chua cá lóc đi"), hệ thống thực hiện RAG context và cung cấp thông tin chi tiết về món ăn cho LLM. Do thiếu các hướng dẫn cụ thể về việc phản hồi hành động và thiếu ví dụ Few-Shot về gọi công cụ, mô hình nhỏ (`ts/gemini-3.1-flash-lite`) bị phân tâm bởi RAG và chỉ tập trung vào việc mô tả dinh dưỡng của món ăn, rồi trả lời khẳng định bằng văn bản rằng "đã ghi vào nhật ký" mà quên không thực tế xuất ra tool call.
- **Cách xử lý**: 
  1. Cập nhật `_TOOL_RULES` trong `system_prompt.py`, bổ sung ràng buộc nghiêm ngặt: khi người dùng đồng ý/yêu cầu lưu sau khi AI gợi ý hoặc hỏi ý kiến, AI bắt buộc phải thực thi tool ghi nhận (`log_meal`, `log_exercise`...) song hành và tuyệt đối không được trả lời suông hay nói dối là đã lưu mà không gọi tool.
  2. Bổ sung mục `=== VÍ DỤ GỌI CÔNG CỤ (TOOL CALLS) ===` vào `_FEWSHOT` trong `system_prompt.py` để hướng dẫn mô hình cách xử lý các câu trả lời khẳng định hoặc yêu cầu lưu từ người dùng bằng cách gọi tool thực tế.

### 11. Các thẻ hành động (ActionCardWidget, _MealActionCard) hiển thị nút "Lưu vào nhật ký" thừa thãi khi chatbot đã tự động lưu thành công
- **Nguyên nhân**: Khi chatbot gọi tool thành công (như `log_meal` / `log_exercise`), nó sẽ sinh ra một thẻ hành động có cấu trúc (StructuredResponse) đi kèm tin nhắn dạng `✅ Đã tự động ghi nhận món...` trong chat history. Tuy nhiên, trước đây các thẻ này luôn render cứng nút "Lưu vào nhật ký" mà không kiểm tra xem hành động đã được chatbot tự động thực thi và lưu trữ trước đó hay chưa.
- **Cách xử lý**:
  1. Cập nhật hàm `_buildActionCards` trong `chatbot_screen.dart` để kiểm tra thuộc tính văn bản của tin nhắn: `final bool showSaveButton = !message.text.contains('✅')`.
  2. Truyền giá trị `onSaveAll: showSaveButton ? ... : null` cho `_MealActionCard` và `onSaveToJournal: showSaveButton ? ... : null` cho `ActionCardWidget`.
  3. Cập nhật `_MealActionCard` và `ActionCardWidget` để ẩn hoàn toàn nút Lưu và căn chỉnh nút "Xem chi tiết" chiếm toàn bộ chiều rộng khi callback lưu tương ứng là `null`.

### 12. Lỗi các biểu tượng Material Icons bị mất/trống không hiển thị trên Flutter Web Release (biến thể Rounded)
- **Nguyên nhân**: Thuật toán Icon Tree-Shaking hoặc lỗi tương thích font glyphs trong Flutter Web Release khiến các biểu tượng Material Icons có biến thể `_rounded` và `_outline_rounded` không thể hiển thị và bị trống hoàn toàn (trong khi các biểu tượng cơ bản không hậu tố vẫn hiển thị bình thường).
- **Cách xử lý**: 
  1. Thay thế tất cả các biểu tượng dạng `Icons.*_rounded` và `Icons.*_outline_rounded` trong ứng dụng bằng các biến thể tiêu chuẩn tương ứng.
  2. Để tránh các lỗi thiếu glyph do sự khác biệt giữa phiên bản SDK Flutter (ví dụ: Flutter 3.12) và phông chữ Material Icons trên Web, thay thế các icon đặc biệt không được hỗ trợ/bị lỗi hiển thị bằng các icon tiêu chuẩn tương đương chắc chắn hiển thị tốt:
     - Biểu tượng Cân nặng: `Icons.scale` ➡️ `Icons.monitor_weight`
     - Biểu tượng Chiều cao: `Icons.straighten` ➡️ `Icons.height`
     - Biểu tượng Mục tiêu: `Icons.track_changes` ➡️ `Icons.flag`
     - Biểu tượng Cài đặt khi không được chọn: `Icons.person_outline` ➡️ `Icons.person_outlined` (đồng bộ đuôi `_outlined` của bộ tab bar).
  3. Biên dịch lại toàn bộ dự án với cờ tắt tree-shaking: `flutter build web --release --no-tree-shake-icons`.

### 13. Cuộc hội thoại ảo (trống) được tự động tạo trong cơ sở dữ liệu ngay cả khi người dùng chưa gửi bất kỳ tin nhắn nào
- **Nguyên nhân**: Trong `chat_gateway.py` (WebSocket gateway), hàm `_ensure_session_exists` (thực hiện truy vấn `INSERT` tạo cuộc trò chuyện mới trong DB) được gọi ngay tại hàm `authenticate()` khi bắt đầu thiết lập kết nối WebSocket. Điều này khiến cho bất kỳ kết nối rỗng nào được mở lên cũng tạo ra một dòng dữ liệu cuộc trò chuyện rác/trống trong cơ sở dữ liệu.
- **Cách xử lý**: Loại bỏ hoàn toàn lệnh gọi `self._ensure_session_exists()` trong hàm `authenticate()`. Giữ lại lệnh gọi này trong phương thức nhận sự kiện `run()` khi nhận được tin nhắn dạng `"chat"` hoặc `"chat_message"`, đảm bảo cuộc hội thoại chỉ thực sự được ghi nhận và tạo trong DB khi và chỉ khi người dùng gửi tin nhắn đầu tiên cho chatbot.

### 14. Lỗi các bài kiểm thử unit test backend bị gãy khi bổ sung gửi trạng thái `send_status`/`send_thought` qua Gateway
- **Nguyên nhân**: Trong môi trường chạy test, đối tượng `FakeGateway` được sử dụng thay thế cho `ChatGateway` thực tế. Đối tượng giả lập này không được định nghĩa các hàm WebSocket mở rộng như `send_status()` hay `send_thought()`, dẫn đến lỗi `AttributeError: 'FakeGateway' object has no attribute 'send_status'` khi chạy test. Đồng thời, việc phân tích token thô để tìm thẻ `<think>` nếu thực hiện gom nhóm hoặc chia tách sai sẽ phá vỡ cấu trúc danh sách token của test (`streamed == chunks`).
- **Cách xử lý**:
  1. Thêm các kiểm tra an toàn `hasattr(gateway, "send_status")` and `hasattr(gateway, "send_thought")` trong `orchestrator.py` trước khi gọi phương thức từ đối tượng `gateway`.
  2. Định nghĩa class `StreamingToken` thừa kế từ `str` để lưu kèm metadata `token_type` mà không làm thay đổi các hành vi so sánh chuỗi thô của Python.
  3. Bổ sung cơ chế phát hiện sớm (shortcut) trong `llm_client.py` để bỏ qua xử lý ký tự riêng lẻ khi không có ký tự `<` trong token và `_tag_buffer` trống, bảo toàn nguyên vẹn ranh giới và số lượng các token thô được phát ra.

### 15. Chatbot gợi ý sai kiểu món ăn so với yêu cầu của người dùng (ví dụ: gợi ý mì hải sản khi người dùng chọn cơm)
- **Nguyên nhân**: Công cụ gợi ý món ăn `suggest_dish` ban đầu chỉ chấp nhận các tham số lọc về `meal_type` (bữa sáng, trưa, tối), `target_kcal` (calo mục tiêu), và `dietary_restrictions` (chay, ít carb...). Không có tham số nào hỗ trợ tìm kiếm theo từ khóa/danh mục món ăn mà người dùng lựa chọn (như "cơm", "bún", "phở"). Do đó, LLM khi gọi công cụ này không thể truyền đạt mong muốn của người dùng, dẫn đến kết quả trả về mang tính ngẫu nhiên hoặc chỉ ưu tiên calo khớp nhất (chọn Mì thay vì Cơm).
- **Cách xử lý**:
  1. Thêm tham số `query: str` vào schema `_SUGGEST_DISH_SCHEMA` và hàm `suggest_dish()` trong `dish.py`. Lớp mô tả schema được cập nhật rõ ràng để LLM tự động nhận diện và trích xuất từ khóa tìm kiếm khi người dùng nêu ra.
  2. Viết hàm tiện ích `_remove_accents` để chuẩn hóa cả từ khóa truy vấn và tên món ăn trong catalog về dạng không dấu, viết thường trước khi so khớp (substring match), đảm bảo độ bao phủ chính xác cao.
  3. Cập nhật `_dispatch_server` trong `tool_dispatcher.py` để bắt và trả về trực tiếp các mã lỗi cụ thể từ `ValueError` (như `"NO_DISH_FOUND"`) giúp LLM chủ động xử lý khi không có món ăn nào khớp với yêu cầu thay vì báo lỗi chung chung `"TOOL_INTERNAL_ERROR"`.
### 16. Lỗi mã hóa UnicodeEncodeError: 'charmap' khi chạy các bài test xuất log tiếng Việt trên Windows
- **Nguyên nhân**: Khi chạy unit test trên terminal Windows PowerShell, môi trường mặc định có thể sử dụng bảng mã `cp1252` thay vì `UTF-8`. Các câu lệnh `print` chứa chuỗi ký tự tiếng Việt có dấu sẽ gây ra lỗi gãy tiến trình chạy test với thông báo lỗi `UnicodeEncodeError: 'charmap' codec can't encode character...`.
- **Cách xử lý**: Tạo hàm bao bọc chuẩn hóa `_clean_for_cp1252` trong [test_adaptive_learning.py](../apps/backend/tests/test_adaptive_learning.py) để ánh xạ tất cả chữ tiếng Việt có dấu về dạng không dấu, và sử dụng `.encode('ascii', errors='ignore').decode('ascii')` trước khi xuất log ra thiết bị đầu cuối trên nền tảng Windows, đảm bảo an toàn tuyệt đối cho toàn bộ chuỗi ký tự hiển thị.

### 17. Lỗi 'docker' is not recognized hoặc chỉ có container Postgres chạy trong Docker và Backend/Frontend không khởi động được
- **Nguyên nhân**: 
  1. Docker Desktop thường cài đặt mặc định cho từng người dùng (User-specific) tại `C:\Users\<Tên_User>\AppData\Local\Programs\DockerDesktop\resources\bin`.
  2. Trong một số trường hợp, biến môi trường `PATH` của hệ thống bị lỗi cú pháp (ví dụ: dư thừa dấu ngoặc kép không khớp như `C:\Program Files\dotnet";`), làm tê liệt trình tìm kiếm đường dẫn của CMD và khiến hệ thống không thể tìm thấy `docker` dù đường dẫn thư mục Docker Desktop đã tồn tại trong PATH.
  3. File [start-all.bat](../start-all.bat) chỉ chạy duy nhất container `postgres` trong Docker (`docker compose up -d postgres`). Backend FastAPI và Web Server được khởi chạy dưới dạng các tiến trình Python cục bộ ngoài Docker. Nếu lệnh Docker bị thất bại, kịch bản sẽ dừng lại (pause), khiến Backend và Frontend không được khởi chạy.
- **Cách xử lý**:
  1. Cập nhật file [start-all.bat](../start-all.bat) và [stop-all.bat](../stop-all.bat) tự động quét các thư mục cài đặt mặc định của Docker Desktop (trong AppData cá nhân hoặc Program Files). Nếu tìm thấy, kịch bản sẽ gán trực tiếp đường dẫn tuyệt đối của file thực thi vào biến `%DOCKER_CMD%` và gọi trực tiếp (ví dụ: `%DOCKER_CMD% compose up`), bỏ qua việc phụ thuộc vào biến `PATH` của hệ thống.
  2. Hãy đảm bảo Docker Desktop đã được khởi động và ở trạng thái "Engine running" trước khi chạy kịch bản.
  3. Đảm bảo cổng 8080 và 3000 không bị chiếm dụng và dịch vụ LLM đã sẵn sàng.

### 18. Lỗi lệch byte khi chạy stop-all.bat (ví dụ: '⏹️' is not recognized..., 'ho', 'cker' không phải là lệnh hợp lệ)
- **Nguyên nhân**: Windows Command Prompt (cmd.exe) đọc tệp tin theo mã hóa ANSI/ASCII mặc định của hệ thống. Nếu tệp kịch bản `.bat` lưu ở dạng UTF-8 và chứa các ký tự Unicode nhiều byte (như biểu tượng cảm xúc/emoji: `⏹️`, `✅`), trình phân tích cú pháp của CMD sẽ đọc lệch các byte ký tự tiếp theo. Điều này dẫn đến việc các lệnh chuẩn như `echo` bị nuốt mất 2 byte đầu tiên và đọc thành `ho`, hoặc `docker` thành `cker`.
- **Cách xử lý**: Loại bỏ hoàn toàn các ký tự Unicode nhiều byte (emoji, ký tự tiếng Việt có dấu đặc biệt) khỏi các tệp kịch bản `.bat` để đảm bảo chúng chỉ chứa văn bản mã hóa ASCII tiêu chuẩn, tương thích hoàn hảo trên mọi hệ thống Windows mà không cần cấu hình trang mã (code page).

### 19. Lỗi Jinja Exception: System message must be at the beginning khi thay đổi mô hình LLM mới (Qwen 3.5 / LM Studio)
- **Nguyên nhân**: Một số mô hình LLM hiện đại (như Qwen 3.5 hoặc các mô hình dùng chat template Jinja nghiêm ngặt trong LM Studio / Ollama / vLLM) yêu cầu danh sách tin nhắn (`messages`) chỉ được phép chứa tối đa **một** tin nhắn hệ thống (`system` message) và tin nhắn này bắt buộc phải nằm ở đầu danh sách (chỉ số 0).
  1. Trong [orchestrator.py](../apps/backend/services/agent/orchestrator.py) tại bước áp chót của ReAct loop (`step == step_budget - 2`), kịch bản đã thêm một tin nhắn dạng `{"role": "system", "content": "Đã đủ dữ liệu..."}` vào cuối mảng `messages`, khiến template Jinja báo lỗi 500 khi gọi API completion.
  2. Tại [llm_client.py](../apps/backend/services/agent/llm_client.py), `chat()` trước đây chuyển nguyên mảng `messages` vào API mà không lọc/chuẩn hóa vai trò cho các tin nhắn phụ.
- **Cách xử lý**:
  1. Cập nhật [orchestrator.py](../apps/backend/services/agent/orchestrator.py) tại `step == step_budget - 2` sử dụng vai trò `user` kèm chỉ dẫn dạng `[HỆ THỐNG: Đã đủ dữ liệu...]` thay vì vai trò `system`.
  2. Bổ sung cơ chế phòng vệ tự động (Sanitization) trong hàm `chat()` của [llm_client.py](../apps/backend/services/agent/llm_client.py): quét toàn bộ danh sách `messages` và tự động chuyển đổi bất kỳ tin nhắn nào có `role == "system"` tại chỉ số `i > 0` thành tin nhắn vai trò `user` với định dạng `[Chỉ dẫn hệ thống: ...]`.
  3. Bổ sung unit test chống tái phát trong [test_llm_client.py](../apps/backend/tests/test_llm_client.py).

### 20. Lỗi ghi nhận bữa ăn sai calo (lệch về 130 kcal) và lệch món ăn gợi ý so với nhật ký thực tế
- **Nguyên nhân**:
  1. Khi chatbot gọi tool client `log_meal` để ghi nhận bữa ăn, nó chỉ truyền `dish_name` và `meal_type`. Do schema của `log_meal` trên backend không định nghĩa các trường `components` (các thành phần nguyên liệu) và `serving_grams`, mô hình không thể truyền chúng.
  2. Ở phía Flutter client, khi xử lý `log_meal`, nếu không có danh sách thành phần chi tiết từ backend gửi qua, nó sẽ thực hiện so khớp từ khóa món ăn bằng `lookupFoodNutrition`. Vì món ăn *"Cơm giò lụa"* và *"Cơm tôm xào"* đều chứa chữ *"cơm"*, hàm lookup so khớp trúng từ khóa `'cơm'` đầu tiên (có calo là 130 kcal/100g) và gán mặc định serving_grams = 100g, dẫn đến calo bị lệch về 130 kcal.
  3. Khi người dùng hỏi *"bữa sáng đâu?"*, mô hình tự ý gợi ý món *"Cháo lòng"* từ kiến thức nền mà không gọi tool `suggest_dish` (do món này không có trong DB món Việt). Khi người dùng đồng ý lưu, mô hình nhìn vào lịch sử tool call trước đó (đã gọi `suggest_dish` cho bữa sáng và trả về *"Cơm giò lụa"*) để phát lệnh `log_meal(meal_type='breakfast', dish_name='Cơm giò lụa')`, tạo ra sự bất nhất giữa nội dung chữ tư vấn và dữ liệu thực tế lưu vào DB.
- **Cách xử lý**:
  1. Cập nhật schema của tool `log_meal` trong [__init__.py](../apps/backend/services/agent/tools/__init__.py) bổ sung thêm tham số optional `serving_grams` và `components` (chứa mảng các thành phần nguyên liệu chi tiết với đầy đủ calo/macros của từng thành phần).
  2. Bổ sung các chỉ dẫn nghiêm ngặt trong [system_prompt.py](../apps/backend/services/agent/system_prompt.py) yêu cầu mô hình (a) BẮT BUỘC dùng tool `suggest_dish` khi gợi ý món (kể cả khi người dùng đổi món/hỏi bữa thiếu), (b) BẮT BUỘC truyền đầy đủ mảng `components` và `serving_grams` lấy từ kết quả tool gợi ý sang `log_meal` để lưu chính xác thành phần và calo, (c) món lưu trong tool phải trùng khớp tuyệt đối với món đã hiển thị bằng chữ cho người dùng.
  3. Cập nhật logic xử lý `log_meal` trong [ai_chat_provider.dart](../apps/mobile/lib/providers/ai_chat_provider.dart) để ưu tiên parse mảng `components` được truyền từ backend (chia tỷ lệ để quy về hệ calo/macros trên 100g tương thích với cách tính của `MealItem`) trước khi fallback về lookup từ khóa mặc định.

### 21. Lỗi kế hoạch (Plan) được AI thông báo tạo thành công nhưng không hiển thị trong ứng dụng
- **Nguyên nhân**:
  1. Khi người dùng yêu cầu lập kế hoạch, chatbot gọi tool `create_plan`. Do tool `get_user_profile` trên client trước đó không trả về trường `user_id` / `id` thực tế của người dùng đang đăng nhập (ví dụ: `mflIcn3wMtT7YPwCSPQy1d8tmhO2`), mô hình đã tự điền tham số giả định `user_id: "user_001"`. Kế hoạch được ghi vào bảng `plans` của PostgreSQL dưới `user_id = 'user_001'`.
  2. Khi ứng dụng Flutter truy vấn kế hoạch kích hoạt của người dùng hiện tại qua endpoint `GET /plans/{user_id}/active`, cơ sở dữ liệu không tìm thấy bản ghi nào khớp với `user_id` thực tế, dẫn đến lỗi 404 (hoặc lỗi 500 ValidationError do trường `id` kiểu `UUID` trong PostgreSQL chưa được ép kiểu thành chuỗi `str` cho model Pydantic `PlanSummary`).
  3. Phía Flutter `chatbot_screen.dart` trước đó chỉ gọi `_loadActivePlan()` một lần duy nhất lúc khởi tạo widget (`initState`), không tự động làm mới lại khi quá trình streaming của AI hoàn tất.
- **Cách xử lý**:
  1. Cập nhật [chat_gateway.py](../apps/backend/services/agent/chat_gateway.py) và [ai_chat_provider.dart](../apps/mobile/lib/providers/ai_chat_provider.dart) để luôn truyền và đồng bộ `user_id` của tài khoản người dùng thực trong mọi payload tin nhắn WebSocket và kết quả công cụ `get_user_profile`.
  2. Cập nhật [tool_dispatcher.py](../apps/backend/services/agent/tool_dispatcher.py) tự động gán đè `call.arguments["user_id"]` bằng `gateway.user_id` đã xác thực của phiên kết nối đối với các công cụ tạo/truy vấn kế hoạch (`create_plan`, `get_active_plan`...).
  3. Cập nhật [router.py](../apps/backend/modules/plans/router.py) ép kiểu `str(r["id"])` và `str(r["plan_id"])` cho các endpoint trả về `PlanSummary` / `PlanDetail`.
  4. Cập nhật [chatbot_screen.dart](../apps/mobile/lib/features/chat/screens/chatbot_screen.dart) theo dõi trạng thái `isStreaming` để tự động kích hoạt `_loadActivePlan()` ngay khi AI kết thúc lượt phản hồi.

### 22. Ngăn chặn triệt để hiện tượng AI bịa đặt thông tin (Hallucination) và ép buộc phản hồi trung thực
- **Nguyên nhân**:
  1. Khi người dùng yêu cầu các món ăn lạ (như Pizza, đồ Tây không có trong DB món Việt) hoặc các thực phẩm chưa có trong danh mục tra cứu, công cụ `suggest_dish` hoặc `search_food_nutrition` trả về lỗi `NO_DISH_FOUND` hoặc danh sách rỗng `[]`.
  2. Trước đây, hệ thống hướng dẫn mô hình có thể fallback dùng kiến thức nền, dẫn đến nguy cơ mô hình tự bịa tên món ăn, tự đoán số calo/macro ảo và đưa ra các bài tập/lịch sử không có thật trong ứng dụng.
  3. Mô hình có thể nói dối rằng "đã lưu vào nhật ký" mà không thực sự phát lệnh gọi tool tương ứng.
- **Cách xử lý**:
  1. Thiết lập **Tiêu chuẩn Tối cao: Trung thực Tuyệt đối & Chống Bịa đặt (Zero-Hallucination Mandate)** trong [system_prompt.py](../apps/backend/services/agent/system_prompt.py): Bắt buộc 100% dữ liệu (món ăn, bài tập, calo, macro, số liệu người dùng) phải được lấy từ công cụ thật.
  2. Khi công cụ trả về không tìm thấy (`NO_DISH_FOUND`, `NO_FOOD_FOUND`, danh sách rỗng `[]`), AI BẮT BUỘC phải thông báo trung thực, rõ ràng cho người dùng biết rằng cơ sở dữ liệu hiện tại chưa có dữ liệu này và đề xuất đổi tiêu chí/từ khóa, TUYỆT ĐỐI CẤM tự suy diễn số liệu ảo.
  3. Bổ sung từ điển hướng dẫn lỗi `_ERROR_GUIDANCE` trong [orchestrator.py](../apps/backend/services/agent/orchestrator.py) cho các mã lỗi cụ thể (`NO_DISH_FOUND`, `NO_WORKOUT_FOUND`, `NO_FOOD_FOUND`, `TIMEOUT`) để chỉ đạo mô hình thông báo trung thực khi thiếu dữ liệu thay vì tự bịa.
  4. Cấm tuyệt đối việc trả lời bằng chữ khẳng định "đã lưu..." nếu không đồng thời phát lệnh gọi công cụ ghi nhận tương ứng (`log_meal`, `log_exercise`, `log_weight`, `log_lifestyle`, `create_plan`).

### 23. Nút "Xem" kế hoạch kích hoạt trên màn hình Chat gửi tin nhắn hỏi AI thay vì mở giao diện chi tiết
- **Nguyên nhân**:
  1. Trong [chatbot_screen.dart](../apps/mobile/lib/features/chat/screens/chatbot_screen.dart), hàm `_buildActivePlanCard` trước đó gắn sự kiện `onPressed: () => _sendMessage('Xem kế hoạch hiện tại của tôi')` vào nút "Xem", khiến app gửi một tin nhắn chat yêu cầu AI giải thích lại kế hoạch thay vì mở trực tiếp giao diện chi tiết kế hoạch của người dùng.
- **Cách xử lý**:
  1. Tạo component [plan_detail_bottom_sheet.dart](../apps/mobile/lib/widgets/plan_detail_bottom_sheet.dart) hiển thị toàn bộ thông tin kế hoạch sống từ cơ sở dữ liệu (`GET /plans/{user_id}/active/detail`): Mục tiêu, calo/đạm hàng ngày, ngày bắt đầu/kết thúc, danh sách nhiệm vụ từng ngày có kèm checkbox tương tác lưu tiến độ (`updatePlanItemCompletion`).
  2. Gắn sự kiện `onTap` trên toàn bộ thẻ Kế hoạch và nút "Xem" trong [chatbot_screen.dart](../apps/mobile/lib/features/chat/screens/chatbot_screen.dart) để mở trực tiếp `showPlanDetailBottomSheet` native UI thay vì gửi tin nhắn hỏi AI.

### 24. Lỗi lưu thực đơn vào kế hoạch và chiến lược gợi ý cuốn chiếu (3-7 ngày)
- **Nguyên nhân**:
  1. Khi người dùng đồng ý lưu thực đơn cả ngày, chatbot gọi công cụ `append_plan_items` với tham số `plan_id = "placeholder"`. Việc này dẫn đến lỗi cơ sở dữ liệu `asyncpg.exceptions.DataError: invalid input for query argument: 'placeholder' (invalid UUID)` và khiến lượt gọi công cụ bị `TOOL_INTERNAL_ERROR`.
  2. Chatbot cố gắng tự suy diễn món cho cả chu kỳ hoặc sinh thực đơn có tổng calo cả ngày quá thấp (~930 kcal so với mục tiêu 2075 kcal/ngày), không phân bổ theo tỷ lệ chuẩn của từng bữa (Sáng 25-30%, Trưa 35-40%, Tối 30-35%).
- **Cách xử lý**:
  1. Cập nhật [plan_tools.py](../apps/backend/services/agent/tools/plan_tools.py) trong hàm `append_plan_items`: Khi `plan_id` không phải UUID hợp lệ hoặc là giá trị giữ chỗ, hệ thống tự động truy vấn `id` của kế hoạch đang kích hoạt (`status = 'active'`) của người dùng từ cơ sở dữ liệu để thực thi chèn bản ghi an toàn.
  2. Cập nhật chỉ dẫn kiến trúc trong [system_prompt.py](../apps/backend/services/agent/system_prompt.py):
     - Áp dụng chiến lược **Gợi ý thực đơn cuốn chiếu ngắn hạn (3-7 ngày)**: Chỉ gợi ý và lưu lộ trình cho hôm nay, 3 ngày tiếp theo hoặc tối đa 7 ngày tới, tuyệt đối không sinh thực đơn cho toàn bộ chu kỳ 30-60 ngày để tránh quá tải hệ thống và đảm bảo tính linh hoạt thực tế.
     - **Phân bổ calo khoa học**: Chia tỷ lệ calo theo mục tiêu hàng ngày (Sáng 500-600 kcal, Trưa 700-800 kcal, Tối 600-700 kcal) và gọi `suggest_dish` với `target_kcal` tương ứng của từng bữa để tổng calo đạt chuẩn mục tiêu hàng ngày.

### 25. Xử lý lỗi `LLM_UNAVAILABLE` do Upstream API và cơ chế Model Fallback tự động
- **Nguyên nhân**:
  1. Khi chuyển sang máy chủ API `api.vilao.ai`, mô hình `alic/ds/qwen3.5-397b-a17b` thỉnh thoảng gặp tình trạng quá tải hoặc gián đoạn phía upstream (`openai.APIError: Upstream service is temporarily having issues`), khiến backend trả về lỗi `LLM_UNAVAILABLE` cho ứng dụng mobile.
  2. Việc giải mã các streaming chunks chưa có kiểm tra phòng vệ `NoneType` khi stream bị đóng đột ngột từ phía upstream API.
- **Cách xử lý**:
  1. Cập nhật [llm_client.py](../apps/backend/services/agent/llm_client.py):
     - Thêm cơ chế **Auto-Retry với Exponential Backoff**: Tự động thử lại 2 lần khi gặp lỗi mạng/API tạm thời.
     - Thêm cơ chế **Model Fallback Tự động**: Nếu mô hình chính (`alic/ds/qwen3.5-397b-a17b`) gặp sự cố upstream, hệ thống tự động chuyển tiếp yêu cầu sang mô hình phụ (`op/deepseek/deepseek-v4-pro`) mà không làm gián đoạn cuộc trò chuyện của người dùng.
     - Bổ sung kiểm tra an toàn `getattr(chunk, 'choices', None)` và `choice.delta` trong toàn bộ luồng streaming để chống crash `NoneType`.

### 26. Đồng bộ thực đơn lưu vào Màn hình Dinh dưỡng và lỗi Date boundary trong NutritionProvider
- **Nguyên nhân**:
  1. Khi người dùng đồng ý lưu thực đơn hôm nay, chatbot chỉ gọi `append_plan_items` (lưu vào bảng `plan_items` của kế hoạch dài hạn) mà quên phát các lệnh gọi `log_meal` cho từng bữa ăn (sáng, trưa, tối), khiến màn hình Dinh dưỡng (`todayMeals`) vẫn hiển thị "Chưa có bữa ăn nào / Đã ăn 0 kcal".
  2. Trong [nutrition_provider.dart](../apps/mobile/lib/providers/nutrition_provider.dart), hàm `_filterByDate` dùng điều kiện `m.date.isAfter(start)` nên vô tình loại trừ các bữa ăn có timestamp bắt đầu từ `00:00:00` của ngày.
  3. Trong [meal_model.dart](../apps/mobile/lib/models/meal_model.dart), `MealModel.fromMap` chưa bọc an toàn khi parse `date` từ Firestore / Cache dẫn đến `Null check operator used on a null value`.
- **Cách xử lý**:
  1. Cập nhật [system_prompt.py](../apps/backend/services/agent/system_prompt.py): Quy định bắt buộc khi người dùng đồng ý lưu thực đơn hôm nay, AI PHẢI phát các lệnh gọi `log_meal` cho từng bữa ăn (sáng, trưa, tối) để dữ liệu xuất hiện ngay trên màn hình Dinh dưỡng hôm nay, đồng thời gọi `append_plan_items` nếu có kế hoạch.
  2. Sửa `_filterByDate` và `_preFetchNearbyDates` trong [nutrition_provider.dart](../apps/mobile/lib/providers/nutrition_provider.dart) thành `!m.date.isBefore(start) && m.date.isBefore(end)`.
  3. Xử lý an toàn kiểu dữ liệu `date` trong [meal_model.dart](../apps/mobile/lib/models/meal_model.dart).
  4. Biên dịch lại bản dựng Web Flutter Release.

### 27. Đồng bộ tự động món ăn từ Kế hoạch sống (Active Plan) sang Màn hình Dinh dưỡng
- **Nguyên nhân**:
  1. Khi người dùng tạo kế hoạch thực đơn với AI, các món ăn được lưu vào bảng `plan_items` trong cơ sở dữ liệu PostgreSQL của Backend.
  2. Màn hình `NutritionScreen` trước đó chỉ đọc từ Firestore / Local cache mà chưa có cơ chế đồng bộ tự động với API `GET /plans/{user_id}/active/detail` của Backend.
  3. `_NutritionScreenState` thiếu hàm `initState` để kích hoạt `loadTodayMeals` mỗi khi người dùng chuyển sang tab Dinh dưỡng.
- **Cách xử lý**:
  1. Trong [nutrition_provider.dart](../apps/mobile/lib/providers/nutrition_provider.dart): Thêm phương thức `_syncMealsFromBackendPlan` tự động lấy các món ăn (`item_type == 'meal'`) của ngày đang chọn từ `BackendApiService().getActivePlanDetail(userId)` và chuyển đổi thành `MealModel` để đưa vào danh sách `todayMeals` và `allMeals`.
  2. Trong [nutrition_screen.dart](../apps/mobile/lib/features/nutrition/screens/nutrition_screen.dart): Bổ sung `initState` với `WidgetsBinding.instance.addPostFrameCallback` gọi `loadTodayMeals(userId)` để luôn làm mới dữ liệu từ server khi mở tab Dinh dưỡng.
  3. Trong `toggleMealCompleted`: Thêm đồng bộ hai chiều với `BackendApiService().updatePlanItemCompletion(itemId, completed)` để khi người dùng đánh dấu hoàn thành bữa ăn trên tab Dinh dưỡng, trạng thái của Kế hoạch cũng được cập nhật ngay lập tức.
  4. Biên dịch lại bản dựng Flutter Web Release.

### 28. Chuẩn hóa tính năng "Thêm món ăn thủ công" theo CSDL Dinh dưỡng & Món Việt của Backend
- **Nguyên nhân**:
  1. Giao diện thêm món ăn thủ công (`_AddMealSheet`, `_SampleMealsTab`, `_FoodPickerList`) trước đó chỉ sử dụng 5 món mẫu hardcode và danh sách tĩnh ~100 nguyên liệu sơ sài, không đồng bộ với 90 món ăn Việt chuẩn và cơ sở dữ liệu thành phần dinh dưỡng phong phú của Backend mà Chatbot đang sử dụng (`GET /api/nutrition/vietnamese-dishes` và `GET /api/nutrition/vietnamese-foods`).
  2. Khi người dùng muốn tìm hoặc thêm một món ăn quen thuộc (như Phở bò, Cơm tấm, Cháo cá, Canh chua...), giao diện cũ không tự động phân tách thành phần nguyên liệu và tính toán macro chính xác theo công thức của Chatbot.
- **Cách xử lý**:
  1. Trong [nutrition_provider.dart](../apps/mobile/lib/providers/nutrition_provider.dart): Thêm `loadVietnameseDatabase()`, `vietnameseDishes`, `vietnameseFoods` tự động tải và cache 90 món Việt chuẩn cùng toàn bộ dữ liệu dinh dưỡng chi tiết từ Backend.
  2. Trong [nutrition_screen.dart](../apps/mobile/lib/features/nutrition/screens/nutrition_screen.dart):
     - **Tab "⭐ Món Việt" (`_SampleMealsTab`)**: Hiển thị danh mục 90 món Việt chuẩn được phân loại theo loại bữa ăn (Sáng, Trưa, Tối, Phụ) kèm thanh tìm kiếm tức thì. Khi người dùng chọn 1 món, hệ thống tự động tra cứu từng nguyên liệu trong CSDL thực phẩm và phân bổ khối lượng (grams), Calo, Protein, Carbs, Fat chính xác 100% như Chatbot gợi ý.
     - **Tab "🔍 Nguyên liệu" (`_FoodPickerList`)**: Tìm kiếm và chọn từ toàn bộ kho dữ liệu thực phẩm Việt Nam của Backend, hỗ trợ tùy chỉnh khối lượng (grams) và xem trước macro trước khi thêm vào món.
     - **Tính toán Macro thời gian thực**: Tự động tổng hợp và hiển thị trực quan Calo, Đạm, Tinh bột, Chất béo khi thêm/bớt nguyên liệu.
  3. Biên dịch lại bản dựng Flutter Web Release.

### 29. Khắc phục triệt để luồng hiển thị suy nghĩ thực tế của Chatbot (Live AI Reasoning / Chain of Thought)
- **Nguyên nhân**:
  1. Kỹ thuật Assistant Prefilling (`prefill = " "` trong `orchestrator.py`) chèn sẵn 1 khoảng trắng vào role assistant khiến các mô hình lý luận (như `ds/qwen3.5-397b-a17b`) lập tức bỏ qua giai đoạn sinh token suy nghĩ (`reasoning_content` / `<think>`).
  2. Các chỉ dẫn prompt cũ trong `system_prompt.py` và `orchestrator.py` chứa câu cấm suy nghĩ ("Vì bạn đang trả lời trực tiếp mà không qua bước suy nghĩ...", "Gọi tool ngay, im lặng..."), làm triệt tiêu token tư duy của LLM.
  3. `llm_client.py` không ghi nhận `reasoning_content` trong vòng lặp buffer 8 chunk đầu tiên, đồng thời nuốt chửng stream khi phát hiện tool call (`content_stream = None`), khiến toàn bộ lập luận trước khi gọi tool bị biến mất.
  4. Giao diện Chatbot Flutter (`AIThoughtsPanel` & `_buildThinkingBubble`) chỉ hiển thị placeholder tĩnh ("Đang suy nghĩ...") khi không nhận được thought tokens từ backend.
- **Cách xử lý**:
  1. Loại bỏ `prefill = " "` trong `orchestrator.py` để mô hình tự do thực hiện lập luận từng bước (Chain-of-Thought).
  2. Bổ sung mục `=== QUY TRÌNH TƯ DUY & SUY NGHĨ (CHAIN OF THOUGHT) ===` vào `system_prompt.py`, hướng dẫn mô hình tư duy phân tích chi tiết trước khi gọi tool hoặc trả lời.
  3. Cập nhật `llm_client.py`: Lưu trữ an toàn `reasoning_content` trong buffer đầu và tiếp tục phát luồng `StreamingToken(..., "thought")` qua `content_stream` song song với việc trích xuất `tool_calls`.
  4. Nâng cấp `AIThoughtsPanel` trong `chatbot_screen.dart`: Thiết kế giao diện tư duy mượt mà, hiển thị live spinner và icon não bộ phát sáng, định dạng Markdown rõ ràng, tự động mở rộng theo thời gian thực và cho phép đóng/mở linh hoạt khi hoàn tất.
  5. Cập nhật tên mô hình chuẩn xác: `LLM_MODEL=ds/qwen3.5-397b-a17b` trong `config.py` and `.env`.

### 30. Lỗi biên dịch hàng loạt do thiếu từ khóa `async` trong hàm xử lý Tool Call và các cảnh báo linter trong dự án Flutter
- **Nguyên nhân**:
  1. Trong `AIChatProvider`, hàm `_handleToolCall` chứa rất nhiều lệnh gọi bất đồng bộ bằng `await` (như `await _nutritionProvider!.addMeal(...)`, `await _exerciseProvider!.addExercise(...)`, `await _lifestyleProvider!...`, và các API call). Tuy nhiên, hàm này không được khai báo với từ khóa `async`. Lỗi này làm phát sinh hàng loạt lỗi phân tích cú pháp (parser error) do trình biên dịch Dart coi `await` là một định danh/kiểu dữ liệu biến thay vì từ khóa, dẫn đến các lỗi cascading khó hiểu khác.
  2. Phương thức `_preFetchNearbyDates` trong `NutritionProvider` được khai báo nhưng không bao giờ được gọi hoặc sử dụng trong mã nguồn.
  3. Thuộc tính `_error` trong `_PlanDetailSheetState` lưu trữ lỗi chi tiết của kế hoạch nhưng không được sử dụng ở giao diện, làm phát sinh cảnh báo linter. Ngoài ra, widget `Row` chứa các phần tử static không sử dụng từ khóa `const`.
  4. Sử dụng phương thức đã bị deprecated `.withOpacity(opacity)` thay vì `.withValues(alpha: opacity)` cho các giá trị màu sắc trong `main.dart` trên Flutter phiên bản mới.
  5. Cảnh báo sử dụng thư viện web-only `dart:html` trong `location_helper_web.dart` khi build Flutter ngoài môi trường web plugin.
- **Cách xử lý**:
  1. Cập nhật chữ ký hàm `_handleToolCall` trong [ai_chat_provider.dart](../apps/mobile/lib/providers/ai_chat_provider.dart) thành `Future<void> _handleToolCall(Map<String, dynamic> data) async`.
  2. Loại bỏ hoàn toàn phương thức `_preFetchNearbyDates` thừa trong [nutrition_provider.dart](../apps/mobile/lib/providers/nutrition_provider.dart).
  3. Xóa thuộc tính `_error` không dùng đến trong [plan_detail_bottom_sheet.dart](../apps/mobile/lib/widgets/plan_detail_bottom_sheet.dart), log lỗi qua `debugPrint` và tối ưu `Row` thành `const Row(...)`.
  4. Thay thế toàn bộ 22 lệnh gọi `.withOpacity(opacity)` bằng `.withValues(alpha: opacity)` trong [main.dart](../apps/mobile/lib/main.dart).
  5. Bổ sung chú thích `// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter` lên đầu file [location_helper_web.dart](../apps/mobile/lib/utils/location_helper_web.dart).

### 31. Nâng cấp toàn diện giao diện bài tập, phân tách 3 giai đoạn chuẩn thể thao, hướng dẫn kỹ thuật chi tiết, chế độ mô phỏng luyện tập tương tác và theo dõi tiến độ
- **Nguyên nhân**:
  1. Trước đây, khi AI gợi ý các chuỗi bài tập phức hợp (như *Full Body workout (intermediate)*, *Cardio đốt mỡ*, *Upper Body Strength*), hệ thống chỉ gom toàn bộ chuỗi động tác thành một đoạn văn bản thô không cấu trúc (`details['description']`), khiến giao diện `DetailBottomSheet` hiển thị sơ sài và đơn điệu.
  2. Người dùng không thấy được các động tác cụ thể, thiếu số hiệp x số lần cho từng bài, thiếu thông tin nhóm cơ tác động, thiết bị cần dùng, hướng dẫn tư thế (form cues), và kỹ thuật hít thở chuẩn.
  3. Thiếu chế độ mô phỏng luyện tập trực quan và trình phát bài tập theo thời gian thực (Interactive Workout Player) với đồng hồ đếm giờ, đếm hiệp, thời gian nghỉ ngơi (rest interval timer) và thanh theo dõi tiến độ hoàn thành.
- **Cách xử lý**:
  1. Tạo model `WorkoutRoutinePlan`, `WorkoutPhase`, `WorkoutExerciseStep` và bộ parser thông minh `WorkoutRoutineParser` trong [workout_routine_model.dart](../apps/mobile/lib/models/workout_routine_model.dart) tích hợp sẵn từ điển tra cứu kỹ thuật, nhóm cơ, thiết bị và nhịp thở của hơn 30 bài tập phổ biến.
  2. Xây dựng CustomPainter & Widget hoạt ảnh chuyển động mô phỏng [workout_simulation_painter.dart](../apps/mobile/lib/widgets/workout_simulation_painter.dart) mô phỏng chân thực nhịp phát lực, cơ bắp co thắt và chu kỳ hít thở theo từng động tác.
  3. Phát triển màn hình trình phát tương tác [workout_simulation_screen.dart](../apps/mobile/lib/features/exercise/screens/workout_simulation_screen.dart) hỗ trợ đếm giờ, đếm hiệp, đếm thời gian nghỉ ngơi, thanh tiến độ % thời gian thực và màn hình chúc mừng hoàn thành để lưu trực tiếp vào nhật ký vận động.
  4. Nâng cấp giao diện [detail_bottom_sheet.dart](../apps/mobile/lib/widgets/detail_bottom_sheet.dart) theo phong cách Glassmorphism với 3 giai đoạn chuẩn (Khởi động ➔ Thân bài chính ➔ Giãn cơ & Hạ nhiệt), thẻ động tác mở rộng và nút CTA **"Bắt đầu luyện tập"** nổi bật.
  5. Cập nhật [action_card_widget.dart](../apps/mobile/lib/widgets/action_card_widget.dart) hiển thị badge số lượng bài tập và nút mở chi tiết / luyện tập tiện lợi.
  6. Viết bộ kiểm thử unit test và widget test đầy đủ đạt 100% pass (`workout_routine_model_test.dart`, `workout_simulation_test.dart`).

### 33. Lỗi hiển thị chuỗi HTML thô (`<p>...</p>`) và trùng lặp calo tiêu thụ giống hệt nhau (`~284 kcal/30p`) ở mọi bài tập
- **Nguyên nhân**:
  1. Dữ liệu bài tập trích xuất từ wger API (`wger.description`) chứa các thẻ HTML gốc như `<p>`, `</p>`, `&nbsp;`, `<br/>`. Khi nạp vào `ExerciseTemplate` hoặc hiển thị danh mục bài tập (`_showCategorySheet`), hệ thống gán trực tiếp chuỗi này lên widget `Text` mà không loại bỏ thẻ HTML, dẫn đến lỗi hiển thị thô `<p>Zone two Cardio for ...</p>` như người dùng phản ánh.
  2. Hàm tính toán chỉ số chuyển hóa tương đương `_estimateMET` trong `ExerciseProvider` chỉ kiểm tra chuỗi phân loại lớn (ví dụ: `if (cat.contains('cardio')) return 8.0`). Vì toàn bộ 42 bài tập trong mục Cardio đều có `cat == 'cardio'`, tất cả đều bị gán cứng `MET = 8.0`.
  3. Khi tính lượng calo tiêu hao 30 phút theo công thức khoa học `MET * weight(kg) * (30/60)` với người dùng nặng 71kg: `8.0 * 71 * 0.5 = 284 kcal`, dẫn đến hiện tượng mọi bài tập (chạy chậm Zone 2, bơi nước rút 50m, nhảy dây, máy elip, treo người) đều ra đúng số calo `~284 kcal/30p` giống hệt nhau một cách phi thực tế.
- **Cách xử lý**:
  1. Thêm bộ lọc tĩnh `cleanHtml(String html)` trong [exercise_provider.dart](../apps/mobile/lib/providers/exercise_provider.dart) loại bỏ triệt để toàn bộ regex HTML tags và ký tự đặc biệt trước khi đưa lên UI.
  2. Thiết kế hàm đánh giá MET chuẩn thể thao `estimateMETForExercise(name, categoryName, muscleCount)` dựa trên Compendium of Physical Activities:
     - Nước rút / Bơi tốc độ / HIIT / Burpee: `MET 10.0 - 11.5` (~355-408 kcal/30p).
     - Nhảy dây / High Knees / Chạy nhanh: `MET 8.0 - 10.0` (~284-355 kcal/30p).
     - Chạy chậm Zone 2 / Đạp xe vừa: `MET 6.5 - 7.0` (~230-248 kcal/30p).
     - Máy Elliptical / Treo dây TRX: `MET 5.5 - 6.0` (~195-213 kcal/30p).
     - Kháng lực phức hợp (Squat, Deadlift, Bench Press): `MET 5.5 - 7.0`.
     - Kháng lực cô lập (Curl, Extension, Plank, Crunch): `MET 3.8 - 4.5`.
     - Dẻo dai / Yoga / Giãn cơ: `MET 2.5 - 3.5`.
  3. Áp dụng đồng bộ `ExerciseProvider.estimateMETForExercise` trên toàn bộ [exercise_screen.dart](../apps/mobile/lib/features/exercise/screens/exercise_screen.dart), [exercise_detail_screen.dart](../apps/mobile/lib/features/exercise/screens/exercise_detail_screen.dart), [exercise_browser_screen.dart](../apps/mobile/lib/features/exercise/screens/exercise_browser_screen.dart) và [smart_exercise_picker.dart](../apps/mobile/lib/widgets/smart_exercise_picker.dart).
  4. Bổ sung unit test kiểm tra `cleanHtml` và `estimateMETForExercise` trong [workout_routine_model_test.dart](../apps/mobile/test/workout_routine_model_test.dart) (100% pass).

### 34. `start-all.bat` phục vụ bản Flutter Web cũ sau khi mã nguồn đã thay đổi
- **Nguyên nhân gốc**: `start-all.bat` trước đây chỉ mở `serve_web.py`. Server này phục vụ thư mục tĩnh `apps/mobile/build/web` nhưng không gọi `flutter build web`, nên mọi thay đổi mới trong mã Dart, tài nguyên, cấu hình web hoặc dependency chưa được biên dịch vẫn không xuất hiện trên `http://localhost:3000`.
- **Cách xử lý**:
  1. Thêm [web_build_fingerprint.ps1](../apps/mobile/tool/web_build_fingerprint.ps1) để tạo dấu vân tay SHA-256 ổn định từ `lib/`, `web/`, `assets/`, `pubspec.yaml`, `pubspec.lock` và chính quy tắc tính dấu vân tay.
  2. Trước khi mở Web Server, [start-all.bat](../start-all.bat) so sánh dấu vân tay hiện tại với `build/web/.source_hash`. Nếu bản build chưa tồn tại hoặc nội dung đầu vào đã đổi, script chạy `flutter build web --release --no-tree-shake-icons`.
  3. Chỉ ghi dấu vân tay mới sau khi build thành công. Nếu build thất bại, Web Server không khởi động bằng bản cũ và lần chạy sau vẫn tự thử build lại.

### 35. Chatbot hiển thị các trạng thái trung gian dư thừa thay vì chỉ hiện quá trình suy nghĩ
- **Nguyên nhân gốc**: Backend gửi riêng sự kiện `status` (tiến độ kỹ thuật như tải ngữ cảnh, gọi tool) và `thought` (reasoning thực tế), nhưng `AIChatProvider` lưu cả `statusText` vào message và `_buildThinkingBubble` luôn render một bong bóng animated dots/status trước `AIThoughtsPanel`. Vì vậy người dùng thấy các câu trạng thái ngắn, lặp lại và không có giá trị nội dung.
- **Cách xử lý**:
  1. Loại bỏ `statusText` khỏi `AIChatMessage` và bỏ toàn bộ bong bóng `_TypingDots`/status trong `chatbot_screen.dart`.
  2. `_buildThinkingBubble` trả widget rỗng khi chưa có `thought`; khi reasoning bắt đầu truyền về, chỉ render avatar cùng `AIThoughtsPanel` đang cập nhật trực tiếp.
  3. Tiếp tục nhận sự kiện `status` trong `AIChatProvider` nhưng chỉ dùng để reset timeout, không lưu vào state và không gọi `notifyListeners()`.

### 36. Card món ăn khi xem lịch sử khác card lúc đang chat trực tiếp
- **Nguyên nhân gốc**: Card trực tiếp được tạo từ `StructuredResponse` đầy đủ của client tool, nhưng `chat_messages` và API lịch sử trước đây chỉ lưu/trả `content` cùng `thoughts`. Khi mở lịch sử, `AIChatProvider` phải dùng regex đoán tên món từ câu trả lời rồi tự tạo một action 100g với macro fallback; danh sách nguyên liệu và khẩu phần gốc đã mất nên cùng một message cho ra card khác.
- **Cách xử lý**:
  1. Migration `005_chat_message_structured_data.sql` bổ sung cột `structured_data JSONB` cho `chat_messages`.
  2. Client tool `log_meal`/`log_exercise` gửi `ui_message` chứa đúng text và `StructuredResponse.toJson()` đã dùng để render trực tiếp. Payload trình bày này nằm ngoài `data` để không làm phình transcript gửi cho LLM.
  3. `AgentOrchestrator` ghi `ui_message` thành assistant turn kèm `structured_data`; API `/chat/sessions/{session_id}/messages` trả payload dưới trường `structured`.
  4. `AIChatProvider.loadExistingSession` ưu tiên parse payload cấu trúc gốc và chỉ dùng regex fallback cho dữ liệu cũ trước migration.

### 37. Màn Cài đặt chỉ hiển thị thông tin nhưng thiếu chức năng quản lý thực tế
- **Nguyên nhân gốc**:
  1. `AccountSettingsScreen` là trang tĩnh dài, chỉ cho đổi mục tiêu và đăng xuất; mức vận động, chỉ số cá nhân, cấu hình check-in và lịch sử chat không có luồng chỉnh sửa/quản lý.
  2. Nút Trợ lý AI chỉ hiện snackbar hướng dẫn thay vì điều hướng; phiên bản hiển thị bị hardcode không khớp `pubspec.yaml`.
  3. `UserProvider.updateProfile` luôn gọi Firestore, kể cả tài khoản `demo`, nên cập nhật hồ sơ thất bại khi Firebase không khả dụng.
  4. API check-in settings đã tồn tại nhưng mobile không sử dụng; cấu hình backend là cache runtime nên lựa chọn có thể mất sau khi backend restart.
- **Cách xử lý**:
  1. Thiết kế lại `AccountSettingsScreen` theo nhóm và nối các action tới màn hình thật.
  2. Thêm `ProfileSettingsScreen` với validation cho toàn bộ dữ liệu ảnh hưởng BMI/BMR/TDEE và chuẩn hóa các mã mức vận động cũ.
  3. Thêm `CheckinSettingsScreen`; `ProactiveProvider` lưu lựa chọn theo `userId` bằng `SharedPreferences`, đồng bộ backend khi mở app và chặn tải nudge ngay tại client nếu master switch bị tắt.
  4. Thêm `ChatHistorySettingsScreen` để mở/xóa từng phiên hoặc xóa toàn bộ, luôn yêu cầu xác nhận trước thao tác phá hủy.
  5. Cho phép `UserProvider.updateProfile` cập nhật in-memory đối với tài khoản demo, còn tài khoản thật vẫn ghi Firestore như trước.
  6. Siết `GET /chat/sessions`: tài khoản đã xác định chỉ nhận session có cùng `user_id`; khi không truyền user mới chỉ đọc session `anonymous`.

### 38. Nút “Thêm bài tập” nổi che nội dung và trùng chức năng
- **Nguyên nhân gốc**: `ExerciseScreen` khai báo thêm một `FloatingActionButton.extended` trong khi `HomeScreen` đã có nút AI `centerDocked`; đồng thời trạng thái lịch tập trống đã có nút “Thêm bài tập ngay”. Hai FAB chồng vùng hiển thị ở cạnh dưới và tạo thao tác trùng lặp.
- **Cách xử lý**: Gỡ FAB “Thêm bài tập” khỏi `ExerciseScreen`, giữ nút thêm nằm trong nội dung trang và các lối vào từ danh mục bài tập.

### 39. Chatbot không còn nhả chữ liên tục dù WebSocket vẫn dùng streaming
- **Nguyên nhân gốc**: Nhà cung cấp OpenAI-compatible có thể buffer các SSE event ở upstream rồi xả hàng trăm `reasoning_content`/`content` chunk gần như cùng lúc. Backend và `AIChatProvider` vẫn xử lý từng token đúng giao thức, nhưng nhiều lần cập nhật UI xảy ra trong cùng một frame nên người dùng thấy cả câu trả lời xuất hiện tức thì.
- **Cách xử lý**:
  1. Thêm `StreamingTypewriter` phía Flutter để gom các token đang dồn và phát chúng theo nhịp ngắn.
  2. Dùng batch thích ứng theo độ dài backlog: câu ngắn chạy từng grapheme, câu dài tăng dần số grapheme mỗi nhịp để giới hạn thời gian chờ bổ sung.
  3. Trì hoãn xử lý `done` và card/gợi ý cho tới khi hàng đợi typewriter rỗng; đối chiếu `full_response` để bổ sung an toàn phần suffix bị thiếu trong delta.
  4. Xóa timer và backlog khi ngắt kết nối, retry, chuyển session hoặc dispose provider; thought đến muộn không được chuyển message đang trả lời về trạng thái thinking.

### 40. Kế hoạch 7 ngày chỉ hiện Ngày 1, không thấy Ngày 2–7
- **Nguyên nhân gốc**: `PlanDetailBottomSheet` tạo `itemsByDay` trực tiếp từ các bản ghi `plan_items`, rồi lặp qua `itemsByDay.entries`. Nếu database mới có item của Ngày 1 thì map chỉ có key `1`; những ngày chưa được planner/AI ghi dữ liệu không có key nên biến mất hoàn toàn khỏi giao diện. Chỉ số `3/3 xong` cũng chỉ đếm item đang tồn tại, không phản ánh độ phủ 7 ngày của kế hoạch.
- **Cách xử lý**:
  1. Khởi tạo trước toàn bộ `day_index` trong khoảng tuần đang xem rồi mới phân nhóm item thật vào từng ngày.
  2. Ngày không có item vẫn render card với thông báo “Chưa có thực đơn hoặc bài tập cho ngày này” và action nhờ AI bổ sung.
  3. Hiển thị đồng thời số ngày có lịch và số mục hoàn thành; dữ liệu thiếu được báo trung thực, không tự tạo món ăn/bài tập giả ở client.
  4. Bổ sung unit test xác nhận tuần có item ở Ngày 1 vẫn giữ đủ key Ngày 1–7 và bỏ qua item ngoài tuần.

### 41. Panel “AI đang suy nghĩ...” vẫn hiện cả khối, không có hiệu ứng typing
- **Nguyên nhân gốc**: Typewriter trước đó chỉ được nối vào sự kiện `token` của câu trả lời cuối. Sự kiện `thought` vẫn được `_onThoughtReceived` cộng trực tiếp vào chuỗi rồi gọi `notifyListeners()`. Khi upstream buffer reasoning và xả hàng trăm chunk trong cùng một frame, Flutter chỉ kịp vẽ trạng thái cuối nên toàn bộ quá trình suy nghĩ xuất hiện như một khối. Token câu trả lời đến ngay sau đó còn chuyển message sang `streaming`, làm panel reasoning trực tiếp bị ẩn trước khi người dùng quan sát được.
- **Cách xử lý**:
  1. Tạo một `StreamingTypewriter` riêng cho token `thought`, phát reasoning theo grapheme cluster và cập nhật `AIThoughtsPanel` theo từng nhịp.
  2. Giữ token câu trả lời trong bộ đệm trong lúc reasoning còn backlog; khi thought typewriter idle mới bắt đầu phát câu trả lời theo đúng thứ tự.
  3. Sự kiện `done` chờ cả hai typewriter và phần câu trả lời đang giữ chạy hết rồi mới hoàn tất message, gắn card và suggestions.
  4. Reasoning dùng hệ số batch `2` để xử lý nhanh hơn câu trả lời nhưng vẫn giữ chuyển động typing rõ ràng; toàn bộ timer/backlog được dọn ở đầu lượt mới và khi disconnect/dispose.

### 42. Yêu cầu tạo kế hoạch dài hạn nhưng chatbot chỉ làm 1–2 ngày rồi hỏi đi hỏi lại
- **Nguyên nhân gốc**:
  1. Model được giao các tool cấp thấp: tạo header bằng `create_plan`, tự gọi gợi ý cho từng bữa/bài tập, rồi `append_plan_items` theo từng ngày. Một kế hoạch 7 ngày cần hàng chục thao tác nhưng agent chỉ có một số hữu hạn vòng suy luận, nên nó bị buộc chuyển sang trả lời chữ khi mới lưu được Ngày 1–2.
  2. Prompt còn hướng dẫn chỉ điền cuốn chiếu và xin lựa chọn “tự động hay tự chọn”, khiến một yêu cầu đã rõ vẫn phát sinh nhiều lượt xác nhận.
  3. Quick action đã gọi REST planner nhưng sau đó lại gửi cùng yêu cầu vào chat, tạo thêm một luồng plan trùng lặp.
  4. `PlannerAgent` được khởi tạo bằng `ToolRegistry` trong production nhưng `_call_tool` chỉ tìm method trực tiếp, không lấy `descriptor.fn`; endpoint planner vì vậy không thực sự dùng được catalog production một cách ổn định.
- **Cách xử lý**:
  1. Thêm `create_long_term_plan` làm thao tác cấp cao duy nhất: nhận mục tiêu, thời lượng và hồ sơ rồi tạo đủ mọi ngày trong một lần chạy server-side.
  2. `ToolDispatcher` tự chuẩn hóa `user_context` Flutter thành `UserProfile` và dùng mục tiêu của yêu cầu hiện tại, nên model không phải hỏi lại tuổi/cân nặng/chiều cao đã có.
  3. Sửa adapter của `PlannerAgent` để gọi được cả method test và implementation trong `ToolRegistry`; kiểm thử end-to-end bằng catalog món ăn/bài tập thật xác nhận 3 ngày tạo đủ 12 mục.
  4. Plan mới hoàn tất sẽ chuyển các plan active cũ sang `cancelled` nhưng vẫn giữ lịch sử; quick action chỉ tải lại card “Kế hoạch active”, không nhắn chatbot tạo lần hai.
  5. Prompt yêu cầu thực hiện ngay khi dữ liệu đủ, không dừng giữa chừng, và rút reasoning xuống vài câu dễ hiểu thay vì hiển thị nhật ký tool nội bộ.

### 43. Lộ trình 60 ngày bị trình bày như 60 ngày rời rạc thay vì lịch sinh hoạt theo tuần
- **Nguyên nhân gốc**:
  1. Planner trước đây áp dụng một mức calo/protein cho toàn bộ thời lượng và xoay nhóm cơ theo `day_index`; ngày nghỉ chỉ được suy ra bằng phép chia 7 nên không gắn với Thứ Hai–Chủ Nhật thực tế.
  2. Flutter có bộ chọn tuần nhưng chia giai đoạn bằng các mốc tuần hardcode. Với thời lượng khác mẫu ban đầu, giai đoạn không co giãn tương ứng và tuần cuối của 60 ngày bị gọi chung là “Tuần 9” mà không nói đó chỉ là 4 ngày.
  3. `plan_items.payload` không chứa metadata lịch tuần, khiến client chỉ có thể đoán giai đoạn và loại ngày từ số thứ tự.
- **Cách xử lý**:
  1. Chuẩn hóa lộ trình thành các block 7 ngày; `60 ngày = 8 tuần + 4 ngày`, tổng cộng 9 tuần hiển thị và Tuần 9 là tuần rút gọn.
  2. Phân tỷ lệ toàn bộ số tuần vào 4 giai đoạn thích nghi → xây nền → tăng tiến → củng cố. Planner điều chỉnh mục tiêu năng lượng, protein, cấp độ và thời lượng bài tập theo từng giai đoạn.
  3. Chọn buổi tập theo thứ thật của `plan_date`; Chủ Nhật là ngày nghỉ hoàn toàn và các ngày không có buổi tập chính được ghi rõ là phục hồi chủ động.
  4. Ghi `schedule` vào payload của từng món ăn/bài tập, gồm tuần, ngày trong tuần, tên thứ, giai đoạn, loại ngày, mục tiêu dinh dưỡng và cờ tuần rút gọn/refeed.
  5. Flutter ưu tiên metadata do planner sinh ra, nhưng vẫn có fallback cho plan cũ; giao diện hiển thị tuần rút gọn, ngày lịch thực và nhãn buổi tập/phục hồi/nghỉ.

### 44. Chatbot báo đã tạo đủ kế hoạch nhưng màn chi tiết hiện `0/7 ngày có lịch`
- **Triệu chứng**: Bảng `plans` có một plan active và chatbot khẳng định đã tạo xong, nhưng `plan_items` bằng 0; màn kế hoạch hiện “Chưa có thực đơn hoặc bài tập” cho mọi ngày và màn Dinh dưỡng cũng không đồng bộ được món nào.
- **Nguyên nhân gốc**:
  1. Planner tạo item ID bằng cách ghép chuỗi như `<plan-uuid>-1-breakfast`, trong khi `plan_items.id` là cột PostgreSQL `UUID`. Asyncpg từ chối lệnh insert vì ID dài 48 ký tự không phải UUID.
  2. `append_plan_items` bắt mọi exception của database, chỉ ghi warning rồi tiếp tục log “inserted”; `create_plan` cũng có cùng hành vi. Do không có exception truyền lên, planner hoàn tất vòng lặp và tool trả `ok=true`/`days_generated=7` dù database không ghi được item nào.
  3. Khi `plan_id` không hợp lệ hoặc không tồn tại, hàm append còn tự chọn plan active mới nhất toàn hệ thống, có nguy cơ ghi nhầm dữ liệu giữa người dùng.
- **Cách xử lý**:
  1. Sinh UUID v5 xác định từ `plan_id + day_index + item_type`, vừa hợp lệ với schema vừa ổn định khi retry.
  2. Bỏ toàn bộ `try/except` nuốt lỗi ở hai hàm ghi plan. Lỗi database nay làm `PlannerAgent` rollback header và các item đã ghi trước đó, sau đó ToolDispatcher trả lỗi thay vì cho chatbot tuyên bố thành công.
  3. Kiểm tra hậu điều kiện trực tiếp trên `plan_items` trước khi công bố thành công: số ngày có meal phải bằng `duration_days` và số meal phải bằng `duration_days × 3`. Nếu không đủ, trả `PLAN_INCOMPLETE`, rollback plan mới và chưa chuyển plan cũ sang `cancelled`.
  4. Chỉ append vào đúng UUID plan được truyền; UUID sai trả `INVALID_PLAN_ID`, UUID không tồn tại trả `PLAN_NOT_FOUND`.
  5. Bổ sung kiểm thử xác thực UUID của mọi item, lỗi ghi database phải được propagate và coverage thiếu phải rollback.
  6. Tái tạo plan bị ảnh hưởng bằng đúng profile đã lưu trong tool invocation; xác minh REST trả đủ 21 meal + 4 exercise trên Ngày 1–7.

### 36. Giao diện lịch sử Chatbot mất bảng “Xem quá trình suy nghĩ”
- **Nguyên nhân gốc**: Token `thought` chỉ được truyền trực tiếp qua WebSocket và giữ trong `AIChatMessage` ở bộ nhớ Flutter. Bảng `chat_messages` chỉ có `content`, còn API lịch sử chỉ trả `role/content/created_at`; khi mở lại session, `loadExistingSession` không có reasoning để dựng `AIThoughtsPanel`, khiến cùng một câu trả lời có giao diện khác lúc vừa chat.
- **Cách xử lý**:
  1. Thêm cột `chat_messages.thoughts` bằng migration `004_chat_message_thoughts.sql` và đồng bộ schema khởi tạo mới.
  2. `AgentOrchestrator` gom token có `token_type == "thought"` qua mọi bước gọi tool của một lượt và lưu cùng assistant turn cuối; reasoning vẫn không được đưa ngược vào prompt hội thoại.
  3. Endpoint lịch sử trả trường `thoughts`; Flutter nạp trường này vào `AIChatMessage`, vì vậy nhánh render hoàn tất dùng lại đúng `AIThoughtsPanel` hiện có.
  4. `AIThoughtsPanel` mặc định mở cả khi đã hoàn tất hoặc vừa được nạp từ lịch sử, thay vì tự đóng ngay khi stream kết thúc.
  5. Các message cũ có `thoughts = ''` vì dữ liệu đó không tồn tại trước migration; hệ thống không tự bịa hoặc tái tạo reasoning giả.

### 45. Cập nhật Endpoint và Model Vilao AI (`rk/llms/qwen-3.7-plus` & `spd/deepseek-v4-pro`)
- **Tình huống / Yêu cầu**: Chuyển đổi provider sang API gateway `https://api.vilao.ai/v1` sử dụng API key mới và danh mục model OpenAI-compatible.
- **Nguyên nhân & Cách xử lý**:
  1. Cấu hình `LLM_MODEL=rk/llms/qwen-3.7-plus` làm mô hình chính (nhẹ, nhanh, hỗ trợ native function calling & streaming token trực tiếp).
  2. Cấu hình `HEAVY_LLM_MODEL=spd/deepseek-v4-pro` làm mô hình suy luận sâu cho các ca xử lý phức tạp hoặc dự phòng (fallback) tự động khi mô hình chính gặp sự cố upstream.
  3. Cập nhật `OPENAI_BASE_URL=https://api.vilao.ai/v1` và `OPENAI_API_KEY=sk-a23e051...` trong `apps/backend/.env`, `apps/backend/config.py`, root `.env`, `apps/backend/.env.docker`, `apps/backend/.env.example`.
  4. Kiểm thử trực tiếp với live endpoint: Xác thực health check (`GET /v1/models`), streaming response, non-streaming heavy model và nhận diện tool call chính xác 100%.

### 46. Nhầm lẫn Calo "Đã ăn" vs Calo Kế hoạch dự kiến trên giao diện và Chatbot Prompt
- **Triệu chứng**: Kế hoạch hôm nay có 3 bữa (2544 kcal) ở trạng thái `3 sắp ăn` (chưa ăn bữa nào), nhưng màn Dinh dưỡng hiện `Đã ăn: 2544 kcal, Còn lại: 0 kcal`, và Chatbot cảnh báo `Hôm nay bạn đã nạp 3165 kcal, vượt hơn 600 kcal`.
- **Nguyên nhân gốc**:
  1. `NutritionProvider` trước đây chỉ có `totalCalories` tính tổng toàn bộ các bữa ăn trong ngày bất kể `isCompleted`.
  2. UI màn hình Dinh dưỡng & Trang chủ dùng `totalCalories` hiển thị vào mục "Đã ăn" thay vì chỉ tính các bữa đã hoàn thành.
  3. Mobile Chatbot gửi `todayCalories = totalCalories` (2544 kcal) sang Chatbot và prompt hệ thống cộng dồn món mới đề xuất (~621 kcal) thành `3165 kcal`.
- **Cách xử lý**:
  1. Tách biệt rõ `consumedCalories` (chỉ tính `isCompleted == true`) và `plannedCalories` (tổng calo toàn bộ kế hoạch trong ngày) trong `NutritionProvider`.
  2. Cập nhật `NutritionScreen` và `HomeScreen`: hiển thị "Đã ăn: 0 kcal", "Còn lại: 2544 kcal" khi chưa ăn, và hiển thị rõ "Kế hoạch: 2544 kcal (3 sắp ăn)".
  3. Đồng bộ `ChatbotScreen` chỉ gửi `consumedCalories` và `completedMealsCount`.
  4. Phân nhóm trong prompt hệ thống backend: tách bạch `Bữa đã ăn` và `Bữa dự kiến trong kế hoạch chưa ăn`.

### 48. Đổi món ăn nhưng món cũ trong kế hoạch không bị xóa (xuất hiện cả 2 món cùng lúc)
- **Triệu chứng**: Khi người dùng đồng ý đổi món bữa tối sang **Bún chả**, Chatbot thông báo *"Đã cập nhật món Bún chả vào bữa tối hôm nay"*, nhưng trên màn hình Dinh dưỡng, cả **Cơm đùi gà nấu nấm** (món cũ) và **Bún chả** (món mới) đều cùng xuất hiện trong Bữa tối.
- **Nguyên nhân gốc**:
  1. Hàm `addMeal(meal)` trong `NutritionProvider` trước đây chỉ đơn thuần `_allMeals.add(meal)` và lưu vào Firestore với một ID mới (timestamp).
  2. Món cũ từ kế hoạch active (`Cơm đùi gà nấu nấm`) có `id = plan_item_uuid` vẫn tồn tại trong danh sách `_allMeals`. Khi thêm món mới, hệ thống không dọn dẹp món dự kiến chưa ăn (`isCompleted == false`) của cùng bữa đó.
  3. Khi `_syncMealsFromBackendPlan` chạy lại, nó tiếp tục đồng bộ lại `plan_item_uuid` từ backend PostgreSQL vì chưa có cơ chế đánh dấu ID kế hoạch đã bị người dùng xóa/thay thế.
- **Cách xử lý**:
  1. Cải tiến `addMeal(meal, {bool replacePendingSlot = true})` trong `NutritionProvider`:
     - Tự động quét và tìm các món dự kiến chưa hoàn thành (`!m.isCompleted`) của cùng ngày và cùng loại bữa ăn (`mealType` Sáng/Trưa/Tối).
     - Loại bỏ sạch sẽ các món cũ khỏi `_allMeals`, `_todayMeals`, cache và Firestore.
     - Đưa ID của món cũ vào danh sách `_deletedPlanItemIds` và lưu vào `SharedPreferences`.
  2. Bổ sung bộ lọc trong `_syncMealsFromBackendPlan`:
     - Bỏ qua các `planItemId` nằm trong `_deletedPlanItemIds`.
     - Không tự ý nạp lại món từ backend nếu slot bữa ăn (`date`, `mealType`) đó đã có món mới được người dùng/AI ghi nhận.
  3. Thêm phương thức `replaceMeal(oldMealId, newMeal)` hỗ trợ thay thế slot ăn trực tiếp.
  4. Kiểm thử toàn bộ 70/70 Flutter tests và build web release thành công.

### 48. Carousel màn hình Đăng nhập bị chập chờn, lúc hiện lúc mất và giật lag
- **Triệu chứng**: Khi mở màn hình đăng nhập (`AuthScreen`), thanh slide / carousel giới thiệu tính năng nổi bật (Theo dõi hoạt động, Kế hoạch tập luyện, Dinh dưỡng...) đôi khi bị biến mất hoàn toàn thành khoảng trống màu mint, hoặc bị giật khi chuyển động.
- **Nguyên nhân gốc**:
  1. `_pageController` trong `FeatureCarousel` không được khởi tạo ở `initState()` mà khởi tạo trong `didChangeDependencies()` với `initialPage: 5000 + _activeCard`. Khi `didChangeDependencies()` chạy lại (rebuild, dialog xuất hiện, media query cập nhật), controller cũ bị `dispose()` khi `PageView` vẫn đang gắn kết, gây mất liên kết và lỗi render.
  2. Bố cục `AspectRatio(0.85)` lồng trong `Expanded` và `Center` bên ngoài `PageView` gây xung đột ràng buộc chiều cao/rộng trên các kích thước màn hình khác nhau, khiến widget con bị co về 0 hoặc overflow.
  3. `FeatureCard` sử dụng biến đổi Matrix4 tùy biến (`translateByDouble`/`scaleByDouble`) và lồng `FittedBox` với chiều rộng cố định, gây lỗi gãy layout hoặc chữ bị thu nhỏ quá mức / tràn pixel khi chiều cao màn hình giới hạn.
  4. Timer tự động xoay (`Timer.periodic`) không kiểm tra trạng thái tương tác vuốt của người dùng, dẫn đến xung đột khi người dùng vừa vuốt vừa bị timer kích hoạt chuyển slide.
- **Cách xử lý**:
  1. Khởi tạo `PageController` an toàn trong `initState()` với `viewportFraction: 0.88` (trên mobile) tạo hiệu ứng thẻ nổi peek 2 bên hiện đại, và giải phóng chuẩn xác trong `dispose()`.
  2. Xử lý infinite loop mượt mà với `PageView.builder` và modulo an toàn `index % itemCount`, tự động tạm dừng timer khi người dùng chạm vuốt (`ScrollStartNotification`) và tiếp tục khi thả tay (`ScrollEndNotification`).
  3. Loại bỏ các phép biến đổi Matrix4 lỗi thời trong `FeatureCard`, chuẩn hóa hiệu ứng hover trên Web/Desktop bằng `Matrix4.translationValues(0, -4, 0)`.
  4. Bọc các khối nội dung đồ họa và tiêu đề trong `FittedBox(fit: BoxFit.scaleDown)` với ràng buộc linh hoạt, đảm bảo hiển thị 100% sắc nét, không bị tràn (overflow) trên mọi kích thước thiết bị.
  5. Đạt 100% kiểm thử: 70/70 Flutter tests pass, `flutter analyze` sạch lỗi.

### 49. Đăng xuất xong đăng nhập lại phải reload trang mới vào được app
- **Triệu chứng**: Khi người dùng ấn "Đăng xuất" từ `HomeScreen` hoặc `AccountSettingsScreen`, sau đó đăng nhập lại (Google, Email, hoặc Tài khoản Demo), màn hình bị đứng ở `AuthScreen` và không tự động chuyển vào `HomeScreen`. Người dùng phải ấn F5/Reload trang thì mới vào được ứng dụng.
- **Nguyên nhân gốc**:
  1. Khi khởi động ứng dụng, `main.dart` sử dụng `AuthWrapper` (là một `Consumer<UserProvider>`) làm trang chủ `home`. Khi người dùng đăng nhập lần đầu, `userProvider.notifyListeners()` kích hoạt `AuthWrapper` tự động chuyển sang `HomeScreen`.
  2. Tuy nhiên, trong hàm `_showLogoutDialog` của `HomeScreen` và `AccountSettingsScreen`, sau khi `signOut()` được gọi, code lại thực hiện `Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const AuthScreen()), ...)` đè trực tiếp `AuthScreen` lên gốc Navigation Stack, loại bỏ hoàn toàn `AuthWrapper`.
  3. Khi ở màn `AuthScreen` độc lập này, việc đăng nhập lại tuy cập nhật `_currentUser` trong `UserProvider` nhưng `AuthScreen` không lắng nghe state để tự điều hướng, và `AuthWrapper` đã bị hủy khỏi cây widget.
- **Cách xử lý**:
  1. Tách `AuthWrapper` thành widget độc lập [auth_wrapper.dart](../apps/mobile/lib/features/auth/screens/auth_wrapper.dart).
  2. Cập nhật tất cả các lệnh điều hướng đăng xuất trong [home_screen.dart](../apps/mobile/lib/features/home/screens/home_screen.dart) và [account_settings_screen.dart](../apps/mobile/lib/features/settings/screens/account_settings_screen.dart) sang `pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const AuthWrapper()), ...)`.
  3. Nhờ đó, khi đăng xuất hoặc đăng nhập lại ở bất kỳ thời điểm nào, `AuthWrapper` luôn quản trị trạng thái `isAuthenticated` tự động chuyển đổi giữa `AuthScreen` và `HomeScreen` mượt mà ngay lập tức mà không cần reload trang.
  4. Đạt 100% kiểm thử: 70/70 Flutter tests pass, `flutter analyze` 0 issues.

### 50. Lỗi Google Sign-In / Firebase khi clone project sang máy mới
- **Triệu chứng**: Khi clone dự án sang máy tính khác hoặc cài đặt môi trường mới, người dùng bấm "Đăng nhập bằng Google" thì ứng dụng báo lỗi từ Firebase (`ApiException: 10`, `12500` hoặc không đăng nhập được).
- **Nguyên nhân gốc**:
  1. Google Sign-In trên Android bảo mật dựa vào mã băm chứng chỉ **SHA-1** của file signing key (`debug.keystore`).
  2. Mặc định Android SDK trên mỗi máy tính cá nhân tự sinh một file `debug.keystore` riêng biệt tại `~/.android/debug.keystore` với mã SHA-1 khác nhau.
  3. Khi clone sang máy mới, ứng dụng khi build debug sẽ ký bằng keystore riêng của máy đó chưa được đăng ký trong Firebase Console -> Google Auth chặn truy cập.
- **Cách xử lý**:
  1. Tạo file keystore dùng chung cho môi trường debug đặt tại [apps/mobile/android/app/debug.keystore](../apps/mobile/android/app/debug.keystore).
  2. Cấu hình `signingConfigs.debug` trong cả [build.gradle](../apps/mobile/android/app/build.gradle) và [build.gradle.kts](../apps/mobile/android/app/build.gradle.kts) để Gradle luôn sử dụng file keystore chung này.
  3. Trích xuất mã vân tay SHA-1 và SHA-256 của file keystore chung:
     - **SHA-1**: `DC:60:5D:E3:F6:70:EF:D5:BA:32:B8:1F:F0:91:B1:2F:FB:5B:E9:80`
     - **SHA-256**: `01:78:8F:DF:20:A3:C5:B8:40:53:EC:38:51:64:2E:6C:BC:15:94:70:17:5B:0E:35:26:CA:27:00:8C:A0:71:82`
  4. Đăng ký mã SHA-1 / SHA-256 này vào Firebase Console (Project Settings -> Your Apps -> Android) và commit keystore + config lên Git.
  5. Cập nhật `.gitignore` để giữ lại file `debug.keystore` cho toàn team (`!**/debug.keystore`).
  6. Kết quả: Mọi thành viên clone repo về máy mới đều dùng chung 1 mã ký debug -> Đăng nhập Google hoạt động 100% không cần cấu hình lại.

### 51. Catalog món Việt dùng nguyên liệu thay thế sai và calo không khớp công thức
- **Triệu chứng**:
  1. Tên món và thành phần không cùng một thực phẩm, ví dụ cá basa/cá tuyết bị đổi thành cá rô phi, sò điệp thành tôm, khoai mỡ thành khoai lang hoặc gạo lứt thành gạo trắng.
  2. Nhiều món dùng khối lượng nguyên liệu sống quá lớn nhưng giữ `estimated_calories` thấp; backend phải ép hệ số riêng cho calo trong khi protein/carbs/fat vẫn tính từ nguyên liệu, tạo ra payload không nhất quán.
  3. Catalog không lưu nguồn nên không thể phân biệt công thức đã kiểm chứng với dữ liệu legacy ước lượng.
- **Nguyên nhân gốc**:
  1. `scripts/update_dishes.py` dùng mapping thay thế theo tên để buộc mọi nguyên liệu khớp một dòng trong bảng thực phẩm, kể cả khi hai nguyên liệu khác loài hoặc khác cách chế biến.
  2. Dữ liệu món và bảng 526 thực phẩm không có lớp kiểm định chung về exact match, độ lệch năng lượng và nguồn công thức.
  3. `vietnamese_dishes.json` đồng thời là input của corpus nghiên cứu đóng băng, nên sửa trực tiếp sẽ âm thầm làm thay đổi hash/embedding của thí nghiệm.
- **Cách xử lý**:
  1. Giữ nguyên catalog 90 món làm nguồn frozen; thêm overlay có phiên bản `vietnamese_dishes_curated_v1.json` cho dữ liệu runtime, chứa URL, nhà xuất bản, ngày truy xuất và trạng thái kiểm chứng.
  2. Dùng công thức định lượng của Viện Dinh dưỡng Quốc gia cho Phở bò sốt vang, Phở gà, Cháo gà, Miến gà và Xôi lạc; thêm 6 suất cơm đủ nhóm từ thực đơn tham khảo chính thức.
  3. `modules/nutrition/catalog.py` merge overlay một lần, kiểm tra trùng ID/tên và trả bản sao cho API; `suggest_dish` và Nutrition API dùng cùng catalog 97 món.
  4. Chỉ chấp nhận tên nguyên liệu khớp chính xác Bảng thành phần thực phẩm Việt Nam. Năng lượng món kiểm chứng phải lệch không quá 2% so với tổng `kcal/100g × grams`.
  5. Bộ lọc hải sản/thịt/trứng/sữa dùng mã nhóm thực phẩm của Viện Dinh dưỡng (8xxx/7xxx/9xxx/10xxx), không còn phụ thuộc hoàn toàn vào danh sách tên hardcode.
  6. Sửa route chi tiết món dùng `dish_id: int`; route thực phẩm tra theo `ma_so` hoặc `stt`, khắc phục so sánh ID chuỗi với ID số luôn trả 404.
  7. Chạy `python scripts/validate_dish_catalog.py` để kiểm tra nguồn tin cậy, exact ingredient match, bốn nhóm của suất ăn hoàn chỉnh và độ lệch calo trước khi merge dữ liệu mới.

### 52. Catalog chỉ có 97 món và tăng dữ liệu nhưng mobile vẫn chỉ thấy 100
- **Triệu chứng**: Catalog 97 món không đại diện đủ độ rộng ẩm thực Việt; sau khi thêm dữ liệu vượt 100, ứng dụng vẫn chỉ hiển thị 100 món đầu.
- **Nguyên nhân gốc**:
  1. Batch v1 cố ý nhỏ vì chỉ nhập thủ công công thức từ Viện Dinh dưỡng, không có pipeline nhập hàng loạt.
  2. `GET /api/nutrition/vietnamese-dishes` có `limit=100` mặc định và mobile gọi endpoint không truyền `limit`, tạo trần hiển thị ngầm.
- **Cách xử lý**:
  1. Dùng snapshot ViFoodRec công bố tại PACLIC 2024 làm chỉ mục công thức; chỉ nhận 1.146 bản ghi có nguồn Món Ngon Mỗi Ngày - Ajinomoto Việt Nam, sau đó chọn 203 bản ghi đạt kiểm định để nâng catalog live lên 300.
  2. Không nhập mô tả/cách nấu hoặc tin calo có sẵn; chỉ chuẩn hóa nguyên liệu định lượng, quy về một khẩu phần và tính năng lượng từ Bảng thành phần thực phẩm Việt Nam.
  3. Gắn tầng `normalized_reference_recipe` riêng để không đánh đồng với công thức `verified_*` đối chiếu trực tiếp từ Viện Dinh dưỡng.
  4. Tăng limit mặc định backend và tham số mobile lên 500; validator bắt buộc catalog có đúng 300 món, không trùng ID/tên và 203 món tham khảo phải giữ đủ provenance/độ phủ.

### 53. Gợi ý bài tập coi cable/machine là bodyweight và calo không theo cân nặng
- **Triệu chứng**:
  1. Chọn không có dụng cụ nhưng kết quả có `Biceps Curl With Cable`, `Leg Press Machine` hoặc `Cycling`.
  2. Hai người có cân nặng khác nhau nhận cùng một số kcal; prompt lại nói cố định tập tạ 5 kcal/phút và cardio 8 kcal/phút.
  3. Mọi bài kháng lực đều có 3 hiệp × 10–12 lần, không phụ thuộc trình độ hay mục tiêu.
- **Nguyên nhân gốc**:
  1. Nhiều record wger có `equipment=[]` dù tên bài ghi rõ cable/machine; loader cũ coi mọi danh sách rỗng là bodyweight.
  2. `_REFERENCE_WEIGHT_KG=70` được dùng cố định và dispatcher không gắn cân nặng trong hồ sơ vào tool call.
  3. Tool chưa có tham số mục tiêu và prompt còn mô tả quy tắc calo cũ không khớp implementation MET.
- **Cách xử lý**:
  1. Chỉ coi bodyweight khi wger có sentinel rõ ràng hoặc tên là động tác bodyweight đã biết; phục hồi dụng cụ ghi rõ trong tên.
  2. Dispatcher và planner truyền `weight_kg`; kcal tính theo `MET × 3.5 × kg / 200 × phút` và luôn đánh dấu là ước tính.
  3. Truyền `goal` để chọn sets–reps–rest; nếu có `warning_symptoms`, tool trả `UNSAFE_TO_RECOMMEND_WORKOUT` thay vì sinh buổi tập.
  4. Chạy `pytest -q tests/test_agent_catalog_and_workout_quality.py` để kiểm tra tích hợp 300 món, dụng cụ, cân nặng, mục tiêu và rào chắn an toàn.

### 54. Kế hoạch tăng cơ chỉ tập mỗi nhóm một lần và ngày phục hồi không có bài
- **Triệu chứng**:
  1. Lịch tăng cơ cũ xếp ngực–lưng–chân–vai–tay; mỗi nhóm chính chỉ được chạm trực tiếp một lần/tuần.
  2. Ngày ghi `active_recovery` chỉ có metadata, không có exercise item để người dùng thực hiện.
  3. Toàn bộ giai đoạn củng cố có thể bị giảm thời lượng như deload, kéo dài nhiều tuần.
  4. Hồ sơ 10–17 và 65+ nhận cùng mục tiêu tuần của người 18–64.
- **Cách xử lý**:
  1. Xếp 2–3 buổi full-body không liên tiếp tùy mục tiêu, xen các buổi aerobic/mobility và ngày nghỉ.
  2. Thêm `mobility + recovery` và chỉ chọn động tác cường độ thấp từ catalog; phục hồi được lưu như exercise item bình thường.
  3. Dùng `is_deload_week` chỉ cho tuần cuối; người sedentary/light tăng tần suất sau giai đoạn thích nghi.
  4. Lưu `weekly_activity_target`, `age_band`, `session_type`, `session_intensity`, `planned_duration_minutes` và talk-test cue trong schedule của từng ngày.

### 55. Nhiều nguồn nutrient bị merge ngầm, calo legacy ép hệ số và dị nguyên dựa vào tên
- **Triệu chứng**:
  1. Không biết một nutrient đến từ Vietnam FCT, USDA hay nguồn fallback; thêm nguồn mới có thể ghi đè canonical row.
  2. `suggest_dish` nhân riêng kcal của component để khớp `estimated_calories`, trong khi protein/carbs/fat vẫn lấy từ nguyên liệu, làm cùng payload tự mâu thuẫn.
  3. Raw/cooked không có state, ingredient không có stable food ID/match quality; `UNRESOLVED` có nguy cơ bị thay bằng nguyên liệu gần giống.
  4. Bộ lọc dị nguyên dựa vào vài tên hard-code và region được suy từ tên món mà không có source/confidence.
- **Cách xử lý**:
  1. Dùng `food_source_registry_v1.json`; validator chỉ cho nutrient source trạng thái `ACTIVE` tham gia runtime và coi fallback là lựa chọn thay thế, không phải merge.
  2. `canonical_foods.py` tạo 526 stable IDs, field-level provenance, food state, 5 mức matching, allergen/objective taxonomy và QA `4P+4C+9F`.
  3. Enrich 300 món lúc load; ingredient không exact/close không được publish. Bỏ calorie factor legacy, giữ cả số catalog lẫn recipe-calculated và gắn `catalog_energy_alignment` để audit.
  4. Region chỉ có giá trị khi kèm official cultural URL/confidence; món không có nguồn trả `Unknown`. Yield/retention chưa review được công khai là chưa áp dụng.
  5. Chạy `py -3.10 scripts/validate_dish_catalog.py` và `py -3.10 -m pytest -q tests/test_canonical_food_provenance.py`.

### 56. Hypothesis/dataclasses lỗi trên Python 3.10.0 khi chạy full backend suite
- **Triệu chứng**: Property test dùng immutable dataclass có `slots=True` và
  field `init=False` lỗi trong môi trường Python 3.10.0 dù logic sản phẩm không
  thay đổi; trước đây phải thử runtime-only initializer để xác minh riêng.
- **Nguyên nhân gốc**: Python 3.10.0 là patch đầu tiên, đã lỗi thời; hành vi slots
  của bản này không tương thích với cách Hypothesis 6.151.9 dựng instance trong
  test. Đây là giới hạn của tổ hợp runtime, không phải hành vi business của app.
- **Cách xử lý**:
  1. Giữ major/minor của dự án ở Python 3.10, nâng runtime verification lên
     CPython 3.10.21 thay vì migrate sang 3.11.
  2. Tạo môi trường sạch từ `apps/backend/requirements-e4-py310.lock` và xác
     nhận pip 26.2.1, pytest 8.4.2, Hypothesis 6.151.9.
  3. Chạy lệnh bình thường `python -m pytest -q`; kết quả E4 là 34 passed,
     property tests là 16 passed và full backend là 761 passed, 1 skipped.
  4. Không thêm compatibility shim vào repository và không sửa behavioral code
     chỉ để phục vụ test runtime. Xem runtime artifact
     `apps/backend/data/workout_planner_e4_runtime_v1.json`.

### 61. N3.1 active-learning queue fails module import

- **Symptom:** Python raised `SyntaxError: '(' was never closed` while pytest
  collected the N3/N3.1 suites; no runtime candidate was processed.
- **Root cause:** The nested `tuple(sorted(...))` return in
  `AdaptiveRecipeRepository.active_learning_queue` lost its outer closing
  parenthesis during the initial implementation.
- **Resolution:** Close the outer tuple expression and retain the deterministic
  `(-priority_score, queue_id)` ordering.  The regression test now exercises
  the aggregate-only queue and owner-scoped unknown-dish learning.
- **Regression check:** Run `python -m pytest tests/test_adaptive_nutrition_n3.py
  tests/test_external_recipe_discovery_n3_1.py -q` from `apps/backend`.

### 62. N3.1 redirect security test references the wrong browser fixture

- **Symptom:** The redirect-host test raised `NameError: browser is not
  defined` after the redirect assertion had already passed.
- **Root cause:** The blocked-source assertion from the policy-gate test was
  accidentally placed in the adjacent redirect test while adding the new
  security case.
- **Resolution:** Keep the blocked-source/no-browser-call assertion with its
  `_FakeBrowser` fixture and make the redirect test own only the redirect
  boundary assertion.
- **Regression check:** Run `python -m pytest tests/test_external_recipe_discovery_n3_1.py -q`
  from `apps/backend`.
