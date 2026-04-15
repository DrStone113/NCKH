# Tài Liệu Yêu Cầu

## Giới Thiệu

Hệ thống Chatbot Tư Vấn Sức Khỏe là một ứng dụng hội thoại thông minh được xây dựng trên nền tảng Rasa, sử dụng dữ liệu từ bộ dataset `knowrohit07/know_medical_dialogue_v2` trên Hugging Face. Hệ thống cho phép người dùng đặt câu hỏi về sức khỏe, dinh dưỡng và luyện tập, đồng thời nhận được phản hồi dựa trên độ tương đồng ngữ nghĩa với cơ sở tri thức y tế. Mọi phản hồi đều kèm theo cảnh báo rằng thông tin chỉ mang tính tham khảo và người dùng nên tham vấn bác sĩ chuyên khoa.

---

## Bảng Thuật Ngữ

- **Chatbot**: Hệ thống hội thoại tự động được xây dựng trên Rasa Framework.
- **Dataset_Processor**: Module Python chịu trách nhiệm tải và chuyển đổi dữ liệu từ Hugging Face sang định dạng Rasa YAML.
- **NLU_Pipeline**: Thành phần xử lý ngôn ngữ tự nhiên trong Rasa, bao gồm featurizer và classifier.
- **Intent_Classifier**: Thành phần phân loại ý định của người dùng trong NLU Pipeline.
- **Knowledge_Base**: Cơ sở dữ liệu lưu trữ các cặp câu hỏi-câu trả lời y tế (SQLite hoặc Elasticsearch).
- **Semantic_Retriever**: Module tìm kiếm câu trả lời phù hợp nhất dựa trên độ tương đồng ngữ nghĩa (cosine similarity).
- **Action_Server**: Server thực thi các Custom Action của Rasa (rasa run actions).
- **Custom_Action**: Hàm Python trong `actions/actions.py` được gọi khi Rasa cần xử lý logic phức tạp.
- **Nutrition_API**: API bên ngoài (Nutritionix hoặc WGER) cung cấp thông tin dinh dưỡng và bài tập.
- **Language_Model**: Mô hình ngôn ngữ BERT, RoBERTa hoặc PhoBERT được dùng để tạo vector embedding.
- **Disclaimer**: Cảnh báo bắt buộc đính kèm mọi phản hồi y tế: "Thông tin chỉ mang tính chất tham khảo, hãy tham vấn bác sĩ chuyên khoa."
- **NLU_File**: File `nlu.yml` chứa các ví dụ huấn luyện cho từng intent.
- **Domain_File**: File `domain.yml` định nghĩa intents, entities, slots, responses và actions.
- **Stories_File**: File `stories.yml` định nghĩa các luồng hội thoại mẫu.
- **Food_CSV**: File `food.csv` hoặc `food1.csv` chứa dữ liệu dinh dưỡng USDA cục bộ, với các cột `Category`, `Description`, `Data.Kilocalories`, `Data.Protein`, `Data.Carbohydrate`, `Data.Fat.Total Lipid`, `Data.Fiber` và các vitamin/khoáng chất.
- **Exercise_XLSX**: File `Gym Exercises Dataset.xlsx` chứa dữ liệu bài tập thể dục cục bộ, dùng làm fallback khi Nutrition_API không phản hồi.

---

## Yêu Cầu

### Yêu Cầu 1: Chuẩn Bị và Chuyển Đổi Dữ Liệu

**User Story:** Là một kỹ sư ML, tôi muốn tự động tải và chuyển đổi dataset y tế sang định dạng Rasa YAML, để có thể huấn luyện mô hình mà không cần xử lý thủ công.

#### Tiêu Chí Chấp Nhận

1. THE Dataset_Processor SHALL đọc dữ liệu từ 2 file Parquet cục bộ (`train-00000-of-00002-ffd89d2f2e091165.parquet` và `train-00001-of-00002-f5ea1701ffb671d1.parquet`) thuộc dataset `knowrohit07/know_medical_dialogue_v2`.
2. WHERE các file Parquet cục bộ không tồn tại, THE Dataset_Processor SHALL tải dataset `knowrohit07/know_medical_dialogue_v2` từ Hugging Face Hub bằng thư viện `datasets` như phương án dự phòng.
3. THE Dataset_Processor SHALL đọc thêm file `know_med_v4.json` và hợp nhất dữ liệu vào Knowledge_Base để bổ sung thêm cặp câu hỏi-câu trả lời y tế.
4. WHEN Dataset_Processor nhận được một bản ghi hợp lệ có trường `instruction` và `output`, THE Dataset_Processor SHALL ánh xạ trường `instruction` thành ví dụ huấn luyện cho intent `ask_health_advice` trong NLU_File.
5. WHEN Dataset_Processor nhận được một bản ghi hợp lệ có trường `instruction` và `output`, THE Dataset_Processor SHALL lưu bộ ba (`instruction`, `input`, `output`) vào Knowledge_Base, trong đó trường `input` có thể rỗng.
6. IF trường `instruction` hoặc `output` của một bản ghi bị rỗng hoặc null, THEN THE Dataset_Processor SHALL bỏ qua bản ghi đó và ghi log cảnh báo.
7. THE Dataset_Processor SHALL xuất ra NLU_File hợp lệ theo cú pháp Rasa YAML phiên bản 3.x.
8. WHEN quá trình chuyển đổi hoàn tất, THE Dataset_Processor SHALL in ra tổng số bản ghi đã xử lý thành công và số bản ghi bị bỏ qua từ mỗi nguồn dữ liệu.

---

### Yêu Cầu 2: Cấu Hình NLU Pipeline với Language Model

**User Story:** Là một kỹ sư ML, tôi muốn cấu hình pipeline NLU sử dụng mô hình ngôn ngữ phù hợp, để chatbot hiểu được các câu hỏi y tế phức tạp với độ chính xác cao.

#### Tiêu Chí Chấp Nhận

1. THE NLU_Pipeline SHALL sử dụng `LanguageModelFeaturizer` với mô hình `bert-base-uncased` hoặc `roberta-base` cho dữ liệu tiếng Anh.
2. WHERE ngôn ngữ đầu vào được cấu hình là tiếng Việt, THE NLU_Pipeline SHALL sử dụng `LanguageModelFeaturizer` với mô hình `vinai/phobert-base`.
3. THE Intent_Classifier SHALL phân loại câu hỏi của người dùng vào intent `ask_health_advice` với ngưỡng tin cậy (confidence threshold) tối thiểu là 0.6.
4. IF Intent_Classifier không thể phân loại câu hỏi với confidence >= 0.6, THEN THE Chatbot SHALL kích hoạt intent `nlu_fallback` và yêu cầu người dùng diễn đạt lại câu hỏi.
5. THE NLU_Pipeline SHALL được định nghĩa trong file `config.yml` theo đúng cú pháp Rasa 3.x.

---

### Yêu Cầu 3: Truy Xuất Câu Trả Lời Dựa Trên Độ Tương Đồng Ngữ Nghĩa

**User Story:** Là người dùng cuối, tôi muốn nhận được câu trả lời y tế phù hợp nhất với câu hỏi của mình, để tôi có thể tham khảo thông tin sức khỏe một cách nhanh chóng.

#### Tiêu Chí Chấp Nhận

1. WHEN người dùng gửi một câu hỏi thuộc intent `ask_health_advice`, THE Custom_Action SHALL tính toán vector embedding của câu hỏi bằng Language_Model.
2. WHEN Custom_Action đã tính toán vector embedding của câu hỏi, THE Semantic_Retriever SHALL tìm kiếm trong Knowledge_Base và trả về câu trả lời có cosine similarity cao nhất.
3. THE Semantic_Retriever SHALL trả về kết quả trong vòng 3 giây kể từ khi nhận được vector embedding.
4. IF cosine similarity của kết quả tốt nhất nhỏ hơn 0.5, THEN THE Custom_Action SHALL trả về thông báo "Tôi chưa tìm thấy thông tin phù hợp. Vui lòng tham vấn bác sĩ chuyên khoa."
5. WHEN Custom_Action trả về bất kỳ câu trả lời y tế nào, THE Chatbot SHALL đính kèm Disclaimer vào cuối mỗi phản hồi.
6. THE Knowledge_Base SHALL hỗ trợ lưu trữ tối thiểu 10.000 cặp câu hỏi-câu trả lời.

---

### Yêu Cầu 4: Tích Hợp Thông Tin Dinh Dưỡng và Bài Tập

**User Story:** Là người dùng cuối, tôi muốn hỏi về thông tin dinh dưỡng và bài tập thể dục, để tôi có thể lên kế hoạch chăm sóc sức khỏe phù hợp.

#### Tiêu Chí Chấp Nhận

1. WHEN người dùng gửi câu hỏi thuộc intent `ask_nutrition` hoặc `ask_exercise`, THE Custom_Action SHALL gọi Nutrition_API để lấy thông tin tương ứng.
2. IF Nutrition_API không phản hồi trong vòng 5 giây và intent là `ask_nutrition`, THEN THE Custom_Action SHALL truy vấn Food_CSV theo cột `Description` (tên thực phẩm) và trả về các giá trị `Data.Kilocalories`, `Data.Protein`, `Data.Carbohydrate`, `Data.Fat.Total Lipid` và `Data.Fiber`.
3. IF Nutrition_API không phản hồi trong vòng 5 giây và intent là `ask_exercise`, THEN THE Custom_Action SHALL truy vấn Exercise_XLSX để lấy thông tin bài tập thay thế.
4. IF cả Nutrition_API lẫn dữ liệu cục bộ (Food_CSV hoặc Exercise_XLSX) đều không có dữ liệu phù hợp, THEN THE Custom_Action SHALL trả về thông báo lỗi rõ ràng và đề nghị người dùng thử lại với từ khóa khác.
5. WHEN Custom_Action trả về thông tin dinh dưỡng hoặc bài tập, THE Chatbot SHALL đính kèm Disclaimer vào cuối phản hồi.
6. THE Domain_File SHALL định nghĩa đầy đủ các intents `ask_nutrition` và `ask_exercise`, cùng với các entities tương ứng như `food_item` và `exercise_type`.

---

### Yêu Cầu 5: Hỗ Trợ Đa Ngôn Ngữ (Tiếng Việt)

**User Story:** Là người dùng Việt Nam, tôi muốn đặt câu hỏi sức khỏe bằng tiếng Việt, để tôi có thể sử dụng chatbot một cách tự nhiên và dễ dàng.

#### Tiêu Chí Chấp Nhận

1. WHERE ngôn ngữ được cấu hình là `vi` (tiếng Việt), THE Dataset_Processor SHALL dịch các trường `instruction` và `output` từ tiếng Anh sang tiếng Việt trước khi lưu vào Knowledge_Base.
2. WHERE ngôn ngữ được cấu hình là `vi`, THE NLU_Pipeline SHALL sử dụng PhoBERT thay cho BERT hoặc RoBERTa.
3. THE Chatbot SHALL trả lời bằng cùng ngôn ngữ được cấu hình trong file `config.yml`.
4. IF quá trình dịch thuật thất bại cho một bản ghi, THEN THE Dataset_Processor SHALL giữ nguyên văn bản gốc tiếng Anh và ghi log cảnh báo.

---

### Yêu Cầu 6: Triển Khai và Tích Hợp API

**User Story:** Là một kỹ sư backend, tôi muốn triển khai chatbot và kết nối với nền tảng web/mobile, để người dùng cuối có thể tương tác qua giao diện quen thuộc.

#### Tiêu Chí Chấp Nhận

1. THE Action_Server SHALL khởi động thành công bằng lệnh `rasa run actions` và lắng nghe trên cổng mặc định 5055.
2. THE Chatbot SHALL cung cấp REST API endpoint tại `/webhooks/rest/webhook` để nhận và trả lời tin nhắn theo định dạng JSON.
3. THE Chatbot SHALL hỗ trợ kết nối real-time qua Socket.io tại endpoint `/socket.io`.
4. WHEN Chatbot nhận được một tin nhắn qua REST API, THE Chatbot SHALL trả về phản hồi trong vòng 5 giây.
5. IF Action_Server không thể kết nối đến Knowledge_Base khi khởi động, THEN THE Action_Server SHALL ghi log lỗi chi tiết và dừng khởi động với exit code khác 0.
6. THE Chatbot SHALL được huấn luyện thành công bằng lệnh `rasa train` và tạo ra file model trong thư mục `models/`.

---

### Yêu Cầu 7: An Toàn và Cảnh Báo Y Tế

**User Story:** Là quản trị viên hệ thống, tôi muốn đảm bảo chatbot luôn hiển thị cảnh báo y tế phù hợp, để tránh người dùng hiểu nhầm thông tin tư vấn là chẩn đoán chính thức.

#### Tiêu Chí Chấp Nhận

1. THE Chatbot SHALL đính kèm Disclaimer vào cuối mọi phản hồi liên quan đến sức khỏe, dinh dưỡng hoặc bài tập.
2. THE Disclaimer SHALL có nội dung chính xác: "⚠️ Thông tin chỉ mang tính chất tham khảo, hãy tham vấn bác sĩ chuyên khoa."
3. WHEN người dùng mô tả triệu chứng khẩn cấp (ví dụ: đau ngực, khó thở, mất ý thức), THE Chatbot SHALL ưu tiên hiển thị thông báo khuyến nghị gọi cấp cứu (113/115) trước khi cung cấp bất kỳ thông tin nào khác.
4. THE Chatbot SHALL không đưa ra chẩn đoán bệnh cụ thể hoặc kê đơn thuốc trong bất kỳ phản hồi nào.
