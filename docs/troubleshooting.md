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



