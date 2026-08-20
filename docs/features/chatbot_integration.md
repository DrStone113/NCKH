# 03. Chi Tiết Tính Năng: Chatbot & App Integration

## 🤖 Tổng Quan Tính Năng

Tính năng **Chatbot & App Integration** cho phép AI Trợ Lý hòa làm một với ứng dụng Flutter HealthApp. Trợ lý không chỉ trả lời câu hỏi mà còn truy suất và điều khiển trực tiếp dữ liệu/giao diện ứng dụng.

---

## 🛠️ Danh Sách 15 Client Tools Hoàn Chỉnh

| Domain | Nêu Tool | Mục Đích Sử Dụng |
| :--- | :--- | :--- |
| **Dinh Dưỡng** | `get_user_profile` | Đọc chỉ số tuổi, chiều cao, cân nặng, mục tiêu sức khỏe |
| | `get_today_meals` | Đọc các bữa ăn đã ghi nhận hôm nay kèm calo & macro |
| | `get_meal_log_range` | Đọc nhật ký ăn uống theo khoảng ngày (YYYY-MM-DD) |
| | `log_meal` | Ghi nhận bữa ăn mới vào nhật ký ăn uống |
| **Thể Chất** | `get_today_exercises` | Đọc bài tập đã thực hiện hôm nay kèm thời lượng & calo đốt |
| | `get_exercise_log_range` | Đọc nhật ký vận động theo khoảng ngày |
| | `get_weight_history` | Truy vấn lịch sử biến động cân nặng N ngày |
| | `log_exercise` | Ghi nhận bài tập thể chất mới |
| | `log_weight` | Lưu chỉ số cân nặng hiện tại vào nhật ký |
| **Lifestyle** | `get_lifestyle_logs` | Đọc chỉ số nước uống, giấc ngủ, stress & tâm trạng |
| | `log_lifestyle` | Cập nhật tâm trạng, giấc ngủ hoặc nước uống |
| | `set_lifestyle_reminder` | Thiết lập nhắc nhở sinh hoạt chủ động |
| **Chung & Điều Khiển**| `get_active_plan` | Đọc Kế hoạch active và danh sách mục kế hoạch từ Backend DB |
| | `mark_plan_item_complete` | Đánh dấu bài tập/bữa ăn trong Kế hoạch đã hoàn thành |
| | `navigate_to_screen` | Chuyển đổi màn hình giao diện Flutter (Dashboard, Nutrition, Workout, Lifestyle, Chat) |

---

## 🌟 Floating AI Assistant & Smart AI Health Nudges

1. **Floating AI Assistant (FAB)**: Bong bóng AI hiện diện trên tất cả các tab, mở nhanh cửa sổ trò chuyện dạng bottom sheet mà không làm ngắt gián trải nghiệm người dùng.
2. **AI Health Nudge Card**: Tự động phát hiện thiếu hụt chỉ số sức khỏe trong ngày (ví dụ: nước uống < 1000ml, thiếu nhật ký ăn uống) và hiển thị thẻ cảnh báo thân thiện ngay trên Dashboard.

---

## ⚡ Dynamic System Prompt & Personalization Engine

Hệ thống System Prompt được kiến trúc để tự động biến đổi động theo từng người dùng dựa trên 3 trụ cột dữ liệu sống từ ứng dụng:

1. **Thể Trạng Cá Nhân & Chỉ Số Nhân Trắc Học**:
   - Tự động tính toán và nhúng: **BMI** & Phân loại thể trạng Châu Á/Việt Nam, **BMR** (Mifflin-St Jeor), **TDEE** (Năng lượng tiêu thụ hàng ngày theo mức vận động), **Nhu cầu nước** ($kg \times 0.033$), Chiều cao, Cân nặng hiện tại, Cân nặng mục tiêu.
   - Thể trạng đặc biệt (Gầy / Thừa cân): Tự động điều chỉnh khuyến nghị an toàn cho khớp và chế độ dinh dưỡng tương ứng.
2. **Mục Tiêu Sức Khỏe & Nguyên Tắc Can Thiệp Cá Nhân Hóa (Goal Directives)**:
   - **Giảm cân (`lose_weight`)**: Kích hoạt nguyên tắc thâm hụt calo (-300 đến -500 kcal dưới TDEE, không dưới 1200 kcal), tăng đạm và chất xơ no lâu, phối hợp tập kháng lực + cardio đốt mỡ.
   - **Tăng cơ (`gain_muscle`)**: Kích hoạt nguyên tắc thặng dư calo (+300 đến +500 kcal trên TDEE), mục tiêu đạm cao (1.6 - 2.2g/kg), tập kháng lực quá tải lũy tiến (progressive overload) và chú trọng phục hồi.
   - **Duy trì (`maintain`)**: Giữ calo cân bằng quanh TDEE, đa dạng hóa vi chất, tối ưu năng lượng sinh hoạt.
3. **Đồng Bộ Dữ Liệu Hoạt Động Thực Tế Trong Ngày (Today's Live Logs)**:
   - Tự động theo dõi calo đã nạp (`today_calories_consumed`), calo đã đốt (`today_calories_burned`), calo còn lại có thể ăn (`remaining_calories`).
   - Tóm tắt danh sách bữa ăn và bài tập đã ghi nhận hôm nay, giúp AI luôn căn chỉnh khẩu phần gợi ý bữa tiếp theo vừa vặn với số calo còn lại trong ngày.

---

## 🧠 Đồng Bộ Giao Diện Lịch Sử

- Mỗi assistant turn lưu riêng `content` và `thoughts` trong PostgreSQL. Reasoning chỉ phục vụ giao diện “Xem quá trình suy nghĩ”, không được chèn lại vào context gửi cho LLM.
- API lịch sử trả `thoughts` cùng nội dung tin nhắn để Flutter khôi phục cùng `AIThoughtsPanel` đã dùng trong phiên chat trực tiếp.
- Các client tool tạo card giao diện gửi `ui_message.structured` riêng với kết quả tool. Backend lưu payload vào `chat_messages.structured_data`; trường này không được đưa vào transcript của LLM.
- API lịch sử trả payload dưới tên `structured`, sau đó Flutter khôi phục bằng `StructuredResponse.fromJson` và render qua cùng `_buildActionCards`/`MealSummaryCard` của phiên chat trực tiếp. Vì vậy tên món, nguyên liệu, khẩu phần và macro không bị tính đoán lại khi xem lịch sử.
- Các session được tạo trước migration `004_chat_message_thoughts.sql` vẫn đọc bình thường nhưng không có reasoning cũ để hiển thị.
- Các session được tạo trước migration `005_chat_message_structured_data.sql` vẫn đọc bằng fallback legacy; card chính xác đầy đủ áp dụng cho các message được ghi sau migration.
