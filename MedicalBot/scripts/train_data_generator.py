import json
import re
import os

# Lấy thư mục hiện tại của script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# File dữ liệu đầu vào
INPUT_FILE = os.path.join(SCRIPT_DIR, 'medical_knowledge_base.json')
# File kết quả đầu ra
NLU_FILE = os.path.join(SCRIPT_DIR, 'data', 'nlu_faq.yml')
DOMAIN_FILE = os.path.join(SCRIPT_DIR, 'domain_faq.yml')

def clean_key(text):
    """Tạo key chuẩn cho RASA (không dấu, không ký tự lạ)"""
    return re.sub(r'[^a-zA-Z0-9_]', '_', text).lower()

def extract_topic_from_advice(advice):
    """Trích xuất chủ đề từ nội dung advice"""
    if not advice:
        return "thông tin y tế"
    
    # Lấy câu đầu tiên (thường là tiêu đề)
    first_line = advice.split('\n')[0].strip()
    
    # Loại bỏ các từ không cần thiết
    first_line = re.sub(r'^(SKĐS|Theo|Bác sĩ|Chuyên gia|Nghiên cứu)\s*[-:]?\s*', '', first_line, flags=re.IGNORECASE)
    
    # Tìm các từ khóa y tế phổ biến
    medical_keywords = [
        'tiêu chảy', 'viêm xoang', 'thoát vị', 'vitamin', 'sỏi thận', 'đột quỵ', 
        'mỡ máu', 'ung thư', 'cúm', 'sốt', 'ho', 'đau đầu', 'đau bụng', 'táo bón',
        'cao huyết áp', 'tiểu đường', 'gout', 'viêm họng', 'viêm phổi', 'hen suyễn',
        'dị ứng', 'mất ngủ', 'đau lưng', 'đau khớp', 'loãng xương', 'thiếu máu',
        'suy thận', 'gan nhiễm mỡ', 'trĩ', 'viêm dạ dày', 'viêm ruột', 'sỏi mật'
    ]
    
    # Tìm từ khóa y tế trong câu
    for keyword in medical_keywords:
        if keyword in first_line.lower():
            return keyword
    
    # Nếu không tìm thấy, lấy 3-5 từ đầu có nghĩa
    words = re.findall(r'[\w\u00C0-\u1EF9]+', first_line)
    # Loại bỏ các từ quá ngắn
    words = [w for w in words if len(w) > 2]
    topic = ' '.join(words[:4])
    
    return topic if topic else "thông tin y tế"

def generate_natural_questions(topic):
    """Tạo các câu hỏi tự nhiên từ topic"""
    questions = [
        topic,
        f"Tôi bị {topic} phải làm sao",
        f"Cách chữa {topic}",
        f"Triệu chứng của {topic}",
        f"Thông tin về {topic}",
        f"{topic} là gì",
        f"Làm thế nào để điều trị {topic}",
        f"Nguyên nhân gây {topic}",
        f"Cách phòng ngừa {topic}",
        f"Tôi muốn hỏi về {topic}"
    ]
    return questions

def shorten_advice(advice, max_length=500):
    """Rút gọn advice để phù hợp với RASA response"""
    if len(advice) <= max_length:
        return advice
    
    # Lấy phần đầu và thêm dấu ...
    return advice[:max_length].rsplit(' ', 1)[0] + "... (Xem thêm thông tin chi tiết)"

def generate_training_data():
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ Không tìm thấy file dữ liệu JSON!")
        return

    nlu_content = "version: \"3.1\"\n\nnlu:\n"
    domain_responses = "version: \"3.1\"\n\nresponses:\n"
    
    print(f"🚀 Đang chuyển đổi {len(data)} bài viết thành dữ liệu Training...")
    
    processed = 0
    for key, item in data.items():
        advice = item.get('advice', '')
        if not advice or len(advice) < 50:  # Bỏ qua các entry quá ngắn
            continue
        
        # Trích xuất topic từ advice
        topic = extract_topic_from_advice(advice)
        
        # Tạo intent name ngắn gọn hơn
        intent_name = clean_key(topic)[:50]
        
        # Tạo dữ liệu NLU với câu hỏi tự nhiên
        nlu_content += f"- intent: faq/{intent_name}\n"
        nlu_content += "  examples: |\n"
        
        questions = generate_natural_questions(topic)
        for q in questions:
            nlu_content += f"    - {q}\n"
        nlu_content += "\n"
        
        # Tạo response ngắn gọn
        short_advice = shorten_advice(advice)
        # Escape quotes
        short_advice = short_advice.replace('"', '\\"').replace('\n', ' ')
        
        domain_responses += f"  utter_faq/{intent_name}:\n"
        domain_responses += f"  - text: \"{short_advice}\"\n\n"
        
        processed += 1
        if processed % 500 == 0:
            print(f"  Đã xử lý: {processed}/{len(data)}")

    # Tạo thư mục data nếu chưa tồn tại
    os.makedirs(os.path.dirname(NLU_FILE), exist_ok=True)
    
    # Lưu file NLU
    with open(NLU_FILE, 'w', encoding='utf-8') as f:
        f.write(nlu_content)
    
    # Lưu file Domain
    with open(DOMAIN_FILE, 'w', encoding='utf-8') as f:
        f.write(domain_responses)

    print(f"✅ Xong! Đã tạo {processed} intents:")
    print(f"  - {NLU_FILE}")
    print(f"  - {DOMAIN_FILE}")
    print(f"\n📝 Bước tiếp theo:")
    print(f"  1. Copy nội dung từ {DOMAIN_FILE} vào domain.yml")
    print(f"  2. File {NLU_FILE} đã sẵn sàng để train")

if __name__ == "__main__":
    generate_training_data()
