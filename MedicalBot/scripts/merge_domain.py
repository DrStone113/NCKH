"""
Script để merge domain_faq.yml vào domain.yml
"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAIN_FILE = os.path.join(SCRIPT_DIR, 'domain.yml')
DOMAIN_FAQ_FILE = os.path.join(SCRIPT_DIR, 'domain_faq.yml')

def merge_domains():
    """Merge FAQ responses vào domain.yml"""
    
    # Đọc domain.yml
    with open(DOMAIN_FILE, 'r', encoding='utf-8') as f:
        domain_content = f.read()
    
    # Đọc domain_faq.yml
    with open(DOMAIN_FAQ_FILE, 'r', encoding='utf-8') as f:
        faq_content = f.read()
    
    # Kiểm tra xem đã merge chưa
    if 'utter_faq/' in domain_content:
        print("⚠️ Domain.yml đã chứa FAQ responses. Bỏ qua merge.")
        return
    
    # Loại bỏ header của domain_faq.yml
    faq_lines = faq_content.split('\n')
    faq_responses = []
    in_responses = False
    
    for line in faq_lines:
        if line.strip() == 'responses:':
            in_responses = True
            continue
        if in_responses:
            faq_responses.append(line)
    
    # Thêm FAQ responses vào domain.yml
    faq_responses_text = '\n'.join(faq_responses)
    
    # Tìm vị trí responses: trong domain.yml
    if 'responses:' in domain_content:
        # Thêm vào cuối phần responses
        domain_content = domain_content.rstrip() + '\n' + faq_responses_text
    else:
        # Thêm phần responses mới
        domain_content = domain_content.rstrip() + '\n\nresponses:\n' + faq_responses_text
    
    # Lưu lại domain.yml
    with open(DOMAIN_FILE, 'w', encoding='utf-8') as f:
        f.write(domain_content)
    
    print("✅ Đã merge domain_faq.yml vào domain.yml thành công!")
    print(f"📝 File domain.yml đã được cập nhật với {len(faq_responses)} dòng FAQ responses")

if __name__ == "__main__":
    merge_domains()
