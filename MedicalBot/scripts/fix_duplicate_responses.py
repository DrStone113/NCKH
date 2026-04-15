"""
Script để fix duplicate responses trong domain.yml
"""
import re
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAIN_FILE = os.path.join(SCRIPT_DIR, 'domain.yml')

def fix_duplicate_responses():
    """Fix duplicate response keys trong domain.yml"""
    
    print("🔍 Đang đọc domain.yml...")
    with open(DOMAIN_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Tìm tất cả response keys
    response_pattern = r'^  (utter_faq/\w+):$'
    responses = {}
    lines = content.split('\n')
    
    print("🔍 Đang tìm duplicate responses...")
    
    new_lines = []
    skip_until = -1
    duplicates_found = 0
    
    for i, line in enumerate(lines):
        if i < skip_until:
            continue
            
        match = re.match(response_pattern, line)
        if match:
            response_key = match.group(1)
            
            if response_key in responses:
                # Duplicate found - skip this response block
                print(f"  ⚠️ Tìm thấy duplicate: {response_key} (dòng {i+1})")
                duplicates_found += 1
                
                # Skip lines until next response or end of responses section
                j = i + 1
                while j < len(lines):
                    # Check if next line is another response key or end of responses
                    if re.match(response_pattern, lines[j]) or lines[j].startswith('actions:') or lines[j].startswith('session_config:'):
                        skip_until = j
                        break
                    j += 1
                continue
            else:
                responses[response_key] = i
        
        new_lines.append(line)
    
    if duplicates_found == 0:
        print("✅ Không tìm thấy duplicate responses!")
        return
    
    # Write back
    print(f"\n📝 Đang ghi lại domain.yml (đã xóa {duplicates_found} duplicates)...")
    with open(DOMAIN_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    
    print(f"✅ Đã fix {duplicates_found} duplicate responses!")
    print(f"📊 Tổng số responses còn lại: {len(responses)}")

if __name__ == "__main__":
    fix_duplicate_responses()
