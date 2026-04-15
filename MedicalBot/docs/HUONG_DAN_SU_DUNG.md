# HƯỚNG DẪN SỬ DỤNG CHATBOT Y TẾ

## Bước 1: Cài đặt môi trường

### ⚠️ YÊU CẦU QUAN TRỌNG
RASA 3.6.0 chỉ hỗ trợ Python 3.8, 3.9 hoặc 3.10 (KHÔNG hỗ trợ 3.11+)

### Kiểm tra phiên bản Python
```bash
# Kiểm tra các phiên bản Python đã cài
py -0

# Nếu có Python 3.10, dùng lệnh này
py -3.10 --version
```

### Cài đặt RASA với Python 3.10

**Cách 1: Sử dụng Python 3.10 trực tiếp**
```bash
# Cài rasa-sdk trước (đã thành công)
py -3.10 -m pip install rasa-sdk==3.6.0

# Cài rasa (có thể gặp lỗi PyYAML trên Windows)
py -3.10 -m pip install rasa==3.6.0
```

**Cách 2: Nếu gặp lỗi PyYAML, cài từng package**
```bash
# Cài PyYAML từ wheel prebuilt
py -3.10 -m pip install --upgrade pip setuptools wheel
py -3.10 -m pip install pyyaml==6.0

# Sau đó cài RASA
py -3.10 -m pip install rasa==3.6.0
```

**Cách 3: Tạo virtual environment (Khuyến nghị)**
```bash
# Tạo virtual environment với Python 3.10
py -3.10 -m venv venv

# Kích hoạt virtual environment
venv\Scripts\activate

# Cài đặt trong virtual environment
pip install --upgrade pip setuptools wheel
pip install rasa-sdk==3.6.0
pip install rasa==3.6.0
```

### Nếu không có Python 3.10
- Tải Python 3.10.11 từ: https://www.python.org/downloads/release/python-31011/
- Chọn "Windows installer (64-bit)"
- Trong quá trình cài đặt, tick vào "Add Python to PATH"

## Bước 2: Chuẩn bị dữ liệu

### Cách 1: Sử dụng script tự động (Windows)

Double-click vào file `start.bat` và chọn:
- Chọn `1` để merge domain files
- Chọn `2` để train model

### Cách 2: Chạy thủ công với Python 3.10

```bash
# Di chuyển vào thư mục dự án
cd "29-1-2026/MedicalBot"

# Nếu dùng virtual environment
venv\Scripts\activate

# Merge domain files
py -3.10 merge_domain.py

# Train model (nếu đã cài RASA thành công)
py -3.10 -m rasa train

# Hoặc nếu trong virtual environment
rasa train
```

## Bước 3: Chạy chatbot

### Cách 1: Sử dụng start.bat (Khuyến nghị)

1. Mở Terminal 1: Double-click `start.bat`, chọn `3` (Chạy action server)
2. Mở Terminal 2: Double-click `start.bat`, chọn `4` (Chạy chatbot shell)

### Cách 2: Chạy thủ công

**Terminal 1 - Action Server:**
```bash
cd "29-1-2026/MedicalBot"
rasa run actions
```

**Terminal 2 - Chatbot:**
```bash
cd "29-1-2026/MedicalBot"
rasa shell
```

## Bước 4: Test chatbot

Sau khi chatbot khởi động, bạn có thể test với các câu hỏi:

### Ví dụ hội thoại:

```
Bạn: Xin chào
Bot: Xin chào! Tôi là trợ lý y tế ảo. Tôi có thể giúp gì cho bạn?

Bạn: Tôi bị tiêu chảy
Bot: [Thông tin về tiêu chảy, triệu chứng, cách điều trị...]

Bạn: Cách chữa viêm xoang
Bot: [Thông tin về viêm xoang...]

Bạn: Triệu chứng của đột quỵ
Bot: [Thông tin về đột quỵ...]

Bạn: Tạm biệt
Bot: Tạm biệt! Chúc bạn sức khỏe!
```

### Các chủ đề y tế có thể hỏi:

- Tiêu chảy, viêm xoang, thoát vị
- Vitamin, mỡ máu, sỏi thận
- Đột quỵ, cao huyết áp, tiểu đường
- Ung thư, cúm, sốt, ho
- Đau đầu, đau bụng, táo bón
- Gout, viêm họng, viêm phổi
- Hen suyễn, dị ứng, mất ngủ
- Đau lưng, đau khớp, loãng xương
- Thiếu máu, suy thận, gan nhiễm mỡ
- Trĩ, viêm dạ dày, viêm ruột

## Các lệnh hữu ích

### Trong RASA shell:
- `/stop` - Dừng chatbot
- `/restart` - Khởi động lại hội thoại
- Ctrl+C - Thoát

### Train lại model:
```bash
rasa train --force
```

### Xem model đã train:
```bash
dir models
```

### Test model với test data:
```bash
rasa test
```

## Xử lý lỗi thường gặp

### Lỗi: "No model found"
**Nguyên nhân:** Chưa train model
**Giải pháp:** Chạy `rasa train`

### Lỗi: "Action server not running"
**Nguyên nhân:** Action server chưa được khởi động
**Giải pháp:** Mở terminal khác và chạy `rasa run actions`

### Lỗi: "Out of memory"
**Nguyên nhân:** Không đủ RAM để train
**Giải pháp:** 
1. Đóng các ứng dụng khác
2. Giảm epochs trong `config.yml` (từ 100 xuống 50)
3. Sử dụng máy có RAM cao hơn

### Bot không trả lời đúng
**Giải pháp:**
1. Kiểm tra đã merge domain_faq.yml chưa: `python merge_domain.py`
2. Train lại model: `rasa train --force`
3. Khởi động lại action server và chatbot

### Lỗi encoding trên Windows
**Giải pháp:** Thêm vào đầu file Python:
```python
# -*- coding: utf-8 -*-
```

## Cấu trúc Knowledge Base

Chatbot sử dụng knowledge base với:
- 8,756 bài viết y tế từ các nguồn uy tín
- 4,598 intents FAQ được tạo tự động
- Mỗi intent có 10 câu hỏi mẫu tự nhiên
- Responses được rút gọn dưới 500 ký tự

## Tùy chỉnh chatbot

### Thêm intent mới:
Chỉnh sửa file `data/nlu.yml`:
```yaml
- intent: ten_intent_moi
  examples: |
    - câu hỏi 1
    - câu hỏi 2
```

### Thêm response mới:
Chỉnh sửa file `domain.yml`:
```yaml
responses:
  utter_ten_intent_moi:
  - text: "Nội dung trả lời"
```

### Thêm rule mới:
Chỉnh sửa file `data/rules.yml`:
```yaml
- rule: Tên rule
  steps:
  - intent: ten_intent
  - action: utter_response
```

## Triển khai lên server

### Chạy API server:
```bash
rasa run --enable-api --cors "*" --port 5005
```

### Tích hợp với website:
Sử dụng Rasa REST API hoặc Rasa Webchat widget

### Tích hợp với Facebook Messenger:
Cấu hình trong `credentials.yml`

## Liên hệ

- Sinh viên: Lê Nhật Bằng
- Giảng viên: TS. Thái Minh Tuấn
- Trường: Đại học Cần Thơ
- Đề tài: THS2025-78
