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
