# 04. Sổ Tay Sửa Lỗi (Troubleshooting Guide)

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
  1. Viết kịch bản khởi chạy [serve_web.py](../HealthApp/health_app/serve_web.py) sử dụng `mimetypes.add_type` đăng ký kiểu MIME chuẩn `font/otf` cho `.otf` và `font/ttf` cho `.ttf`.
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
- **Cách xử lý**: Tạo hàm bao bọc chuẩn hóa `_clean_for_cp1252` trong [test_adaptive_learning.py](../HealthApp/ai_backend/backend/tests/test_adaptive_learning.py) để ánh xạ tất cả chữ tiếng Việt có dấu về dạng không dấu, và sử dụng `.encode('ascii', errors='ignore').decode('ascii')` trước khi xuất log ra thiết bị đầu cuối trên nền tảng Windows, đảm bảo an toàn tuyệt đối cho toàn bộ chuỗi ký tự hiển thị.
