# Kế Hoạch Triển Khai: Health Advice Chatbot

## Tổng Quan

Triển khai hệ thống chatbot tư vấn sức khỏe dựa trên Rasa 3.x với Semantic Retrieval, tích hợp vào Flutter app có sẵn. Các task được sắp xếp theo thứ tự phụ thuộc: setup môi trường → xây dựng data pipeline → action server → cấu hình Rasa → train/test → tích hợp Flutter.

---

## Tasks

- [x] 1. Setup môi trường và cấu trúc dự án Rasa
  - Tạo thư mục `d:\NCKH\MedicalBot\` với cấu trúc: `data/`, `actions/`, `scripts/`, `knowledge_base/`, `tests/unit/`, `tests/property/`
  - Tạo file `requirements.txt` với các dependencies: `rasa==3.x`, `sentence-transformers`, `pandas`, `openpyxl`, `hypothesis`, `datasets`, `pyyaml`
  - Tạo file `endpoints.yml` trỏ action server về `http://localhost:5055/webhook`
  - Tạo file `credentials.yml` bật REST connector và Socket.io connector
  - Tạo các file `__init__.py` trong `actions/` và `tests/`
  - _Yêu cầu: 6.1, 6.2, 6.3_

- [x] 2. Xây dựng DatasetProcessor và Data Pipeline
  - [x] 2.1 Tạo `actions/db_client.py` — SQLite client
    - Implement hàm `init_db(db_path)` tạo 5 bảng: `medical_qa`, `embeddings`, `nutrition`, `exercises`, `conversation_logs` theo schema trong design
    - Implement hàm `batch_insert_medical_qa(records)` và `batch_insert_nutrition(records)` và `batch_insert_exercises(records)`
    - Implement hàm `get_all_embeddings()` trả về list `(id, vector_blob)`
    - Implement hàm `get_answer_by_id(id)` trả về `output` từ `medical_qa`
    - _Yêu cầu: 3.6, 6.5_

  - [x] 2.2 Tạo `scripts/prepare_data.py` — DatasetProcessor entry point
    - Đọc 2 file Parquet cục bộ (`dataset/train-00000-*.parquet`, `dataset/train-00001-*.parquet`) bằng `pandas`
    - Fallback sang `datasets.load_dataset("knowrohit07/know_medical_dialogue_v2")` nếu file không tồn tại
    - Đọc và merge `dataset/know_med_v4.json`
    - Validate từng bản ghi: bỏ qua nếu `instruction` hoặc `output` rỗng/null, ghi `logging.warning`
    - Insert batch vào bảng `medical_qa` với trường `source` phân biệt nguồn
    - In ra `processed_count` và `skipped_count` cho từng nguồn khi hoàn tất
    - _Yêu cầu: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8_

  - [ ]* 2.3 Viết property test cho DatasetProcessor (P1, P2, P4)
    - **Property 1: Bản ghi hợp lệ được lưu đúng vào Knowledge Base (Round-trip)**
    - **Validates: Yêu cầu 1.4, 1.5**
    - **Property 2: Bản ghi không hợp lệ không làm tăng kích thước Knowledge Base**
    - **Validates: Yêu cầu 1.6**
    - **Property 4: Tổng số bản ghi là bất biến**
    - **Validates: Yêu cầu 1.8**
    - Tạo file `tests/property/test_pbt_dataset.py` với `@settings(max_examples=100)`

  - [x] 2.4 Tạo `scripts/prepare_data.py` — xuất NLU YAML và load dữ liệu cục bộ
    - Xuất file `data/nlu.yml` hợp lệ theo cú pháp Rasa 3.x từ các `instruction` đã xử lý (intent `ask_health_advice`)
    - Đọc `dataset/food.csv` / `dataset/food1.csv`, insert vào bảng `nutrition` với các cột: `category`, `description`, `kilocalories`, `protein_g`, `carbohydrate_g`, `fat_total_g`, `fiber_g`
    - Đọc `dataset/Gym Exercises Dataset.xlsx` bằng `openpyxl`, insert vào bảng `exercises`
    - _Yêu cầu: 1.7, 4.2, 4.3_

  - [ ]* 2.5 Viết property test cho NLU YAML và dữ liệu cục bộ (P3, P5)
    - **Property 3: NLU YAML đầu ra luôn có thể parse được**
    - **Validates: Yêu cầu 1.7**
    - **Property 5: Model ngôn ngữ được chọn đúng theo cấu hình**
    - **Validates: Yêu cầu 2.1, 2.2, 5.2**
    - Thêm vào `tests/property/test_pbt_dataset.py`

  - [x] 2.6 Hỗ trợ dịch thuật tiếng Việt trong DatasetProcessor
    - Thêm tham số `--lang vi` vào `prepare_data.py`
    - Khi `lang=vi`: dịch `instruction` và `output` sang tiếng Việt trước khi insert
    - Nếu dịch thất bại (exception hoặc chuỗi rỗng): giữ nguyên bản gốc tiếng Anh, ghi `logging.warning`
    - _Yêu cầu: 5.1, 5.3, 5.4_

  - [ ]* 2.7 Viết property test cho dịch thuật (P13)
    - **Property 13: Dịch thuật thất bại giữ nguyên văn bản gốc**
    - **Validates: Yêu cầu 5.4**
    - Thêm vào `tests/property/test_pbt_dataset.py`

- [ ] 3. Checkpoint — Kiểm tra data pipeline
  - Đảm bảo tất cả tests trong `tests/property/test_pbt_dataset.py` và `tests/unit/test_dataset_processor.py` pass. Hỏi người dùng nếu có vấn đề.

- [x] 4. Xây dựng EmbeddingModel và SemanticRetriever
  - [x] 4.1 Tạo `actions/embedding_model.py` — EmbeddingModel wrapper
    - Implement class `EmbeddingModel` với `__init__(model_name: str)` nạp `sentence-transformers`
    - Implement `encode(text: str) -> np.ndarray` trả về float32 array
    - Implement `serialize(vector: np.ndarray) -> bytes` và `deserialize(blob: bytes) -> np.ndarray`
    - _Yêu cầu: 3.1_

  - [ ]* 4.2 Viết property test cho EmbeddingModel (P7)
    - **Property 7: Embedding serialization round-trip**
    - **Validates: Yêu cầu 3.1**
    - Tạo file `tests/property/test_pbt_retriever.py`

  - [x] 4.3 Tạo `scripts/build_embeddings.py` — tính và lưu embeddings vào DB
    - Đọc tất cả `instruction` từ bảng `medical_qa` chưa có embedding
    - Tính embedding bằng `EmbeddingModel`, serialize thành BLOB
    - Batch insert vào bảng `embeddings`
    - _Yêu cầu: 3.1_

  - [x] 4.4 Tạo `actions/semantic_retriever.py` — SemanticRetriever class
    - Implement `retrieve(query: str, db_client, embed_model) -> dict`
    - Load tất cả embeddings từ DB, tính cosine similarity với query vector
    - Trả về `{answer, similarity_score}` với answer có similarity cao nhất
    - Nếu similarity < 0.5: trả về `{answer: None, similarity_score}`
    - Đảm bảo hoàn thành trong 3 giây
    - _Yêu cầu: 3.2, 3.3, 3.4_

  - [ ]* 4.5 Viết property test cho SemanticRetriever (P8, P9)
    - **Property 8: Retrieval trả về kết quả có similarity cao nhất**
    - **Validates: Yêu cầu 3.2**
    - **Property 9: Ngưỡng similarity quyết định nội dung phản hồi**
    - **Validates: Yêu cầu 3.4**
    - Thêm vào `tests/property/test_pbt_retriever.py`

- [x] 5. Xây dựng Custom Actions
  - [x] 5.1 Tạo `actions/actions.py` — ActionEmergencyAlert
    - Implement `ActionEmergencyAlert` kiểm tra từ khóa khẩn cấp trong message (đau ngực, khó thở, mất ý thức, chest pain, shortness of breath, v.v.)
    - Phản hồi phải chứa "113" hoặc "115" trong 200 ký tự đầu, trước mọi nội dung tư vấn
    - _Yêu cầu: 7.3, 7.4_

  - [ ]* 5.2 Viết property test cho ActionEmergencyAlert (P14)
    - **Property 14: Cảnh báo khẩn cấp xuất hiện ở đầu phản hồi**
    - **Validates: Yêu cầu 7.3**
    - Tạo file `tests/property/test_pbt_safety.py`

  - [x] 5.3 Implement `ActionHealthAdvice` trong `actions/actions.py`
    - Gọi `SemanticRetriever.retrieve()` với câu hỏi của người dùng
    - Nếu có kết quả (similarity >= 0.5): trả về answer + disclaimer
    - Nếu không có kết quả: trả về "Tôi chưa tìm thấy thông tin phù hợp. Vui lòng tham vấn bác sĩ chuyên khoa."
    - Luôn đính kèm disclaimer: `"⚠️ Thông tin chỉ mang tính chất tham khảo, hãy tham vấn bác sĩ chuyên khoa."`
    - _Yêu cầu: 3.2, 3.4, 3.5, 7.1, 7.2, 7.4_

  - [x] 5.4 Implement `ActionNutritionInfo` trong `actions/actions.py`
    - Gọi Nutrition API (Nutritionix/WGER) với timeout 5 giây
    - Fallback: truy vấn bảng `nutrition` theo `description LIKE '%food_item%'`, trả về `kilocalories`, `protein_g`, `carbohydrate_g`, `fat_total_g`, `fiber_g`
    - Nếu cả hai đều không có kết quả: trả về thông báo lỗi rõ ràng, đề nghị thử lại
    - Đính kèm disclaimer vào cuối phản hồi
    - _Yêu cầu: 4.1, 4.2, 4.4, 4.5_

  - [x] 5.5 Implement `ActionExerciseInfo` trong `actions/actions.py`
    - Gọi Nutrition API với timeout 5 giây
    - Fallback: truy vấn bảng `exercises` theo `name LIKE '%exercise_type%'`, trả về `name`, `category`, `muscle_group`
    - Nếu cả hai đều không có kết quả: trả về thông báo lỗi rõ ràng
    - Đính kèm disclaimer vào cuối phản hồi
    - _Yêu cầu: 4.1, 4.3, 4.4, 4.5_

  - [ ]* 5.6 Viết property test cho disclaimer và fallback (P10, P11, P12)
    - **Property 10: Disclaimer luôn xuất hiện trong mọi phản hồi liên quan sức khỏe**
    - **Validates: Yêu cầu 3.5, 4.5, 7.1, 7.2**
    - **Property 11: Fallback cục bộ trả về đầy đủ các trường dinh dưỡng và bài tập**
    - **Validates: Yêu cầu 4.2, 4.3**
    - **Property 12: Không có dữ liệu phù hợp luôn trả về thông báo lỗi (không phải exception)**
    - **Validates: Yêu cầu 4.4**
    - Thêm vào `tests/property/test_pbt_safety.py` và `tests/property/test_pbt_retriever.py`

  - [ ]* 5.7 Viết unit tests cho các Custom Actions
    - Tạo `tests/unit/test_actions.py`: kiểm tra disclaimer, emergency alert, fallback logic, thông báo lỗi
    - _Yêu cầu: 3.4, 3.5, 4.4, 7.1, 7.2, 7.3_

- [ ] 6. Checkpoint — Kiểm tra Action Server
  - Đảm bảo tất cả tests trong `tests/property/test_pbt_safety.py`, `tests/property/test_pbt_retriever.py` và `tests/unit/test_actions.py` pass. Hỏi người dùng nếu có vấn đề.

- [x] 7. Cấu hình Rasa (config, domain, stories, rules)
  - [x] 7.1 Tạo `config.yml` — NLU Pipeline
    - Cấu hình pipeline: `WhitespaceTokenizer` → `LanguageModelFeaturizer` (bert-base-uncased) → `CountVectorsFeaturizer` → `DIETClassifier` → `FallbackClassifier(threshold=0.6)`
    - Cấu hình policies: `TEDPolicy`, `RulePolicy`, `MemoizationPolicy`
    - Hỗ trợ cấu hình `language: vi` để dùng PhoBERT
    - _Yêu cầu: 2.1, 2.2, 2.3, 2.4, 2.5, 5.2_

  - [x] 7.2 Tạo `domain.yml` — Intents, Entities, Slots, Responses, Actions
    - Định nghĩa intents: `ask_health_advice`, `ask_nutrition`, `ask_exercise`, `emergency`, `greet`, `goodbye`, `nlu_fallback`
    - Định nghĩa entities: `food_item`, `exercise_type`, `symptom`
    - Định nghĩa responses: `utter_greet`, `utter_goodbye`, `utter_fallback`, `utter_ask_rephrase`
    - Đăng ký actions: `action_health_advice`, `action_nutrition_info`, `action_exercise_info`, `action_emergency_alert`
    - _Yêu cầu: 4.6, 6.2_

  - [x] 7.3 Tạo `data/stories.yml` và `data/rules.yml`
    - Stories: luồng hội thoại cho health advice, nutrition, exercise, emergency
    - Rules: xử lý `nlu_fallback` (yêu cầu diễn đạt lại), `emergency` (luôn gọi `action_emergency_alert`), `greet`/`goodbye`
    - _Yêu cầu: 2.4, 7.3_

- [ ] 8. Train và kiểm thử Rasa model
  - [ ] 8.1 Tạo `tests/unit/test_semantic_retriever.py`
    - Kiểm tra cosine similarity với KB đã biết trước
    - Kiểm tra ngưỡng 0.5 với các trường hợp biên
    - Kiểm tra trường hợp KB rỗng (không ném exception)
    - _Yêu cầu: 3.2, 3.3, 3.4_

  - [ ]* 8.2 Viết property test cho confidence fallback (P6)
    - **Property 6: Confidence thấp luôn kích hoạt fallback**
    - **Validates: Yêu cầu 2.3, 2.4**
    - Thêm vào `tests/property/test_pbt_retriever.py`

  - [ ] 8.3 Tạo `tests/unit/test_dataset_processor.py`
    - Kiểm tra xử lý bản ghi hợp lệ và không hợp lệ
    - Kiểm tra đọc từng nguồn dữ liệu (Parquet, JSON, fallback HF)
    - Kiểm tra xuất YAML đúng cú pháp Rasa 3.x
    - _Yêu cầu: 1.1, 1.2, 1.3, 1.6, 1.7_

- [ ] 9. Checkpoint — Kiểm tra toàn bộ test suite
  - Chạy `pytest tests/` để đảm bảo tất cả unit tests và property tests pass. Hỏi người dùng nếu có vấn đề.

- [x] 10. Tích hợp Flutter — Cập nhật chat_provider.dart
  - [x] 10.1 Cập nhật `lib/providers/chat_provider.dart` trong Flutter app
    - Thay thế toàn bộ logic rule-based keyword matching bằng HTTP POST đến Rasa REST API
    - Endpoint: `POST http://<host>:5005/webhooks/rest/webhook` với body `{"sender": sessionId, "message": userMessage}`
    - Parse response JSON: lấy trường `text` từ mảng response, ghép nếu có nhiều message
    - Xử lý timeout (5 giây) và lỗi mạng: hiển thị thông báo lỗi thân thiện trong chat
    - Giữ nguyên interface `ChatMessage` model hiện có (không thay đổi `text`, `isUser`, `quickReplies`)
    - _Yêu cầu: 6.2, 6.4_

  - [x] 10.2 Thêm cấu hình base URL cho Rasa server vào Flutter app
    - Tạo hằng số hoặc config cho Rasa server URL (dễ thay đổi giữa dev/prod)
    - Đảm bảo `http: ^1.2.0` đã có trong `pubspec.yaml` (đã có sẵn)
    - _Yêu cầu: 6.2, 6.4_

- [ ] 11. Checkpoint cuối — Kiểm tra tích hợp end-to-end
  - Đảm bảo tất cả unit tests và property tests pass. Kiểm tra `chat_provider.dart` gọi đúng Rasa REST API endpoint. Hỏi người dùng nếu có vấn đề.

---

## Ghi Chú

- Tasks đánh dấu `*` là tùy chọn, có thể bỏ qua để triển khai MVP nhanh hơn
- Mỗi task tham chiếu đến yêu cầu cụ thể để đảm bảo traceability
- Property tests dùng thư viện **Hypothesis** với `@settings(max_examples=100)`
- Mỗi property test phải có comment: `# Feature: health-advice-chatbot, Property N: <property_text>`
- Action Server chạy độc lập: `rasa run actions --port 5055`
- Rasa Server: `rasa run --enable-api --cors "*" --port 5005`
- Flutter app kết nối đến Rasa qua `http://localhost:5005` (dev) hoặc địa chỉ server thực tế (prod)
