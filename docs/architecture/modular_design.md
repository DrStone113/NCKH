# Kiến trúc 3-Module Độc Lập (Modular Multi-Agent Healthcare Architecture)

> **Báo cáo Thiết kế Kiến trúc & Định hướng Nghiên cứu Khoa học (NCKH)**  
> **Dự án**: HealthApp - Hệ thống AI Chatbot Chăm sóc Sức khỏe Toàn diện

---

## 1. Đặt vấn đề & Động lực Kiến trúc (Motivation)

Trong các hệ thống AI Chăm sóc Sức khỏe (Healthcare Conversational AI Systems), việc thiết kế một **Monolithic Agent** đơn lẻ vừa xử lý tính toán dinh dưỡng, phân tích bài tập, vừa tư vấn sức khỏe tinh thần thường dẫn tới các hạn chế nghiêm trọng:
1. **Ảo giác AI (Hallucination)** & **Mất tập trung Context**: Khi prompt context quá dài, LLM dễ chọn sai Tool hoặc tính toán sai chỉ số sinh học.
2. **Độ trễ cao (High Latency)**: Tải toàn bộ danh mục tool làm tăng dung lượng token gửi lên LLM.
3. **Khó kiểm thử & Công bố khoa học**: Rất khó đo lường chính xác hiệu năng (Benchmark) của từng mảng riêng biệt khi các domain bị lồng ghép.

**Giải pháp**: Chuyển đổi sang **Modular Architecture (Multi-Agent System)** chia hệ thống thành **3 Module Độc Lập**:
- **Module 1: Dinh dưỡng (Nutrition Domain)**
- **Module 2: Thể chất (Physical Fitness Domain)**
- **Module 3: Sức khỏe Tinh thần & Lifestyle (Mental & Lifestyle Domain)**

---

## 2. Chi tiết 3 Module Chuyên biệt

```
                             ┌─────────────────────────┐
                             │    User Input (Chat)    │
                             └────────────┬────────────┘
                                          │
                           ┌──────────────▼──────────────┐
                           │  Intent Router Orchestrator │
                           └──────────────┬──────────────┘
                ┌─────────────────────────┼─────────────────────────┐
                │                         │                         │
       ┌────────▼─────────┐      ┌────────▼─────────┐      ┌────────▼─────────┐
       │ Module Dinh Dưỡng │      │ Module Thể Chất  │      │Module Lifestyle  │
       ├──────────────────┤      ├──────────────────┤      ├──────────────────┤
       │ - TDEE/BMR Calc  │      │ - Workout Plan   │      │ - Mood Check-in  │
       │ - Meal Composition│     │ - METs & Burned  │      │ - Sleep & Stress │
       │ - Menu Suggestion│      │ - Exercise Guide │      │ - Hydration      │
       └──────────────────┘      └──────────────────┘      └──────────────────┘
```

### Module 1: Dinh dưỡng (Nutrition Domain)
- **Chức năng**:
  - Tính toán TDEE/BMR cá thể hóa theo công thức Harris-Benedict & Mifflin-St Jeor.
  - Phân tích thành phần bữa ăn qua NLP/Vision và giải phẫu thực đơn Việt Nam (Bún riêu, Phở bò, Cơm tấm...).
  - Gợi ý thực đơn cá thể hóa phù hợp với bệnh lý (tiểu đường, cao huyết áp) hoặc mục tiêu thể trạng.
- **Tools**: `calculate_tdee`, `search_food_nutrition`, `get_today_meals`, `get_meal_log_range`, `log_meal`.

### Module 2: Thể chất (Physical Fitness Domain)
- **Chức năng**:
  - Thiết lập lịch tập luyện cá thể hóa (Gym, Cardio, Yoga, Muscle Groups từ Wger database).
  - Phân tích lượng calo tiêu hao dựa trên chỉ số METs (Metabolic Equivalent of Task).
  - Cảnh báo an toàn tập luyện và theo dõi xu hướng cân nặng.
- **Tools**: `get_today_exercises`, `get_exercise_log_range`, `log_exercise`, `log_weight`, `get_weight_history`.

### Module 3: Sức khỏe Tinh thần & Lifestyle (Mental & Lifestyle Domain)
- **Chức năng**:
  - Check-in tâm trạng (Mood Tracking 1-5 sao + Sentiment Analysis).
  - Theo dõi số giờ ngủ và chỉ số căng thẳng (Stress Scale).
  - Theo dõi lượng nước uống (Hydration Progress) và cảnh báo uống nước an toàn (<500ml/lần, <5000ml/ngày).
  - Thiết lập các nhắc nhở sinh hoạt chủ động (Nudge theory).
- **Tools**: `get_lifestyle_logs`, `log_lifestyle`, `set_lifestyle_reminder`.

---

## 3. Lợi ích cho Nghiên cứu Khoa học (NCKH) & Đăng Bài báo

Cấu trúc 3 Module cho phép nhóm nghiên cứu công bố độc lập nhiều bài báo khoa học chất lượng cao:

1. **Bài báo 1 (Dinh dưỡng)**:  
   *Title*: *"Cá thể hóa thực đơn dinh dưỡng Việt Nam dựa trên mô hình ngôn ngữ lớn LLM kết hợp RAG và giải thuật phân tách nguyên liệu"*
2. **Bài báo 2 (Thể chất)**:  
   *Title*: *"Hệ thống khuyến nghị lịch tập luyện thích ứng (Adaptive Fitness Recommendation System) kết hợp cơ sở dữ liệu Wger và chỉ số METs"*
3. **Bài báo 3 (Lifestyle & Tâm lý)**:  
   *Title*: *"Đánh giá hiệu quả của Agent theo dõi tâm trạng và nhắc nhở sinh hoạt chủ động (Nudge Theory) trong việc cải thiện chất lượng sống"*
4. **Bài báo Tổng quan (Master System Paper)**:  
   *Title*: *"Kiến trúc Multi-Agent phân tán trên môi trường di động cho ứng dụng Chăm sóc Sức khỏe Toàn diện"*

---

## 4. Kiểm thử & Đánh giá (Evaluation Metrics)

- **Routing Accuracy**: Đánh giá tỷ lệ Intent Router phân loại chính xác câu hỏi vào 1 trong 3 Module (>95%).
- **Task Success Rate**: Tỷ lệ hoàn thành tool call hợp lệ mà không phát sinh lỗi.
- **Response Latency**: Phản hồi word-by-word streaming đạt dưới 1 giây.
- **System Usability Scale (SUS)**: Khảo sát trải nghiệm người dùng trên cả 3 màn hình tính năng Flutter.
