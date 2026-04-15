"""
Script dịch song ngữ SIÊU TỐC v2 (Anh - Việt) — GPU + Đa luồng tối ưu
- know_med_v4.json  -> know_med_v4_bilingual.json
- food.csv          -> food_bilingual.csv
- Gym Exercises Dataset.xlsx -> Gym Exercises Dataset_bilingual.xlsx
"""

import json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import torch
from transformers import MarianMTModel, MarianTokenizer
from queue import Queue

# Tắt warning
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
import warnings
warnings.filterwarnings('ignore', message='.*unauthenticated.*')

# ── Cấu hình ──────────────────────────────────────────────────────────────────
DATASET_DIR  = os.path.join(os.path.dirname(__file__), "..", "dataset")
CHECKPOINT   = 50         # Lưu checkpoint mỗi N bản ghi
MAX_LENGTH   = 256        # Giảm xuống 256 để nhanh hơn (đủ cho hầu hết câu)

# Batch size và workers
BATCH_SIZE_GPU = 16       # Batch size mỗi lần dịch
NUM_WORKERS = 4           # Số luồng song song (4 luồng x 16 batch = 64 câu cùng lúc)
BATCH_SIZE_CPU = 4
NUM_WORKERS_CPU = 2

# Model
MODEL_NAME = "Helsinki-NLP/opus-mt-en-vi"

# Global
_model_lock = threading.Lock()
_save_lock = threading.Lock()
_model = None
_tokenizer = None
_device = None
BATCH_SIZE = None
NUM_WORKERS_ACTIVE = None


def _init_model():
    """Load model 1 lần duy nhất."""
    global _model, _tokenizer, _device, BATCH_SIZE, NUM_WORKERS_ACTIVE
    if _model is not None:
        return
    
    with _model_lock:
        if _model is not None:
            return
        
        print("🚀 Đang load model dịch...")
        has_cuda = torch.cuda.is_available()
        _device = torch.device("cuda" if has_cuda else "cpu")
        
        BATCH_SIZE = BATCH_SIZE_GPU if has_cuda else BATCH_SIZE_CPU
        NUM_WORKERS_ACTIVE = NUM_WORKERS if has_cuda else NUM_WORKERS_CPU
        
        _tokenizer = MarianTokenizer.from_pretrained(MODEL_NAME)
        _model = MarianMTModel.from_pretrained(
            MODEL_NAME,
            use_safetensors=True
        ).to(_device)
        _model.eval()
        
        if has_cuda:
            gpu_name = torch.cuda.get_device_name(0)
            print(f"   ✅ GPU: {gpu_name}")
        else:
            print(f"   ⚠️  CPU mode (chậm)")
        
        print(f"   ⚡ {NUM_WORKERS_ACTIVE} workers x {BATCH_SIZE} batch = {NUM_WORKERS_ACTIVE * BATCH_SIZE} câu song song\n")


def translate_batch(texts: list[str]) -> list[str]:
    """Dịch batch text - thread-safe."""
    _init_model()
    
    if not texts:
        return []
    
    valid_texts = [t if t and isinstance(t, str) and t.strip() else "" for t in texts]
    non_empty_idx = [i for i, t in enumerate(valid_texts) if t]
    non_empty_texts = [valid_texts[i] for i in non_empty_idx]
    
    if not non_empty_texts:
        return [""] * len(texts)
    
    try:
        # Tokenize
        inputs = _tokenizer(
            non_empty_texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH
        ).to(_device)
        
        # Generate (tắt beam search để nhanh)
        with torch.no_grad():
            translated = _model.generate(
                **inputs,
                max_length=MAX_LENGTH,
                num_beams=1,
                do_sample=False
            )
        
        # Decode
        results = _tokenizer.batch_decode(translated, skip_special_tokens=True)
        
        # Ghép lại
        output = [""] * len(texts)
        for i, result in zip(non_empty_idx, results):
            output[i] = result
        
        return output
    
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        return valid_texts


def _print_progress(current, total, label="", elapsed=0):
    pct = current / total * 100
    bar_len = 40
    filled = int(bar_len * current / total)
    bar = "█" * filled + "░" * (bar_len - filled)
    
    # Tính ETA
    if elapsed > 0 and current > 0:
        rate = current / elapsed
        remaining = (total - current) / rate if rate > 0 else 0
        eta = f"ETA: {int(remaining//60)}m{int(remaining%60)}s"
    else:
        eta = "ETA: --"
    
    print(f"\r  {label} [{bar}] {current}/{total} ({pct:.1f}%) | {eta}", end="", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# 1. know_med_v4.json — Đa luồng tối ưu
# ══════════════════════════════════════════════════════════════════════════════
def _translate_med_batch(args):
    """Worker function: dịch 1 batch."""
    batch_idx, batch_items = args
    
    instructions = [item.get("instruction", "") for item in batch_items]
    outputs = [item.get("output", "") for item in batch_items]
    
    instructions_vi = translate_batch(instructions)
    outputs_vi = translate_batch(outputs)
    
    results = []
    for i, item in enumerate(batch_items):
        results.append({
            "instruction_en": item.get("instruction", ""),
            "instruction_vi": instructions_vi[i],
            "input": item.get("input", ""),
            "output_en": item.get("output", ""),
            "output_vi": outputs_vi[i],
        })
    
    return batch_idx, results


def translate_medical_json():
    src = os.path.join(DATASET_DIR, "know_med_v4.json")
    dst = os.path.join(DATASET_DIR, "know_med_v4_bilingual.json")

    print("\n" + "="*60)
    print("📄 Dịch know_med_v4.json (GPU + Đa luồng)")
    print("="*60)

    _init_model()

    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Load checkpoint
    if os.path.exists(dst):
        with open(dst, "r", encoding="utf-8") as f:
            results_list = json.load(f)
        start = len(results_list)
        results_dict = {i: v for i, v in enumerate(results_list)}
        print(f"  ↩ Tiếp tục từ bản ghi {start}/{len(data)}")
    else:
        results_dict = {}
        start = 0

    total = len(data)
    remaining = data[start:]
    
    # Chia thành các batch
    batches = []
    for i in range(0, len(remaining), BATCH_SIZE):
        batch_items = remaining[i:i+BATCH_SIZE]
        batch_idx = start + i
        batches.append((batch_idx, batch_items))
    
    print(f"  📦 Tổng {len(batches)} batches | {NUM_WORKERS_ACTIVE} workers\n")
    
    # Xử lý đa luồng
    start_time = time.time()
    done = start
    
    with ThreadPoolExecutor(max_workers=NUM_WORKERS_ACTIVE) as executor:
        futures = {executor.submit(_translate_med_batch, batch): batch[0] for batch in batches}
        
        for future in as_completed(futures):
            batch_idx, batch_results = future.result()
            
            with _save_lock:
                for i, result in enumerate(batch_results):
                    results_dict[batch_idx + i] = result
                
                done = len(results_dict)
                elapsed = time.time() - start_time
                _print_progress(done, total, "📄 Med", elapsed)
                
                # Checkpoint
                if done % CHECKPOINT == 0 or done == total:
                    ordered = [results_dict[i] for i in range(total) if i in results_dict]
                    with open(dst, "w", encoding="utf-8") as f:
                        json.dump(ordered, f, ensure_ascii=False, indent=2)

    # Lưu cuối
    ordered = [results_dict[i] for i in range(total) if i in results_dict]
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
    
    elapsed = time.time() - start_time
    print(f"\n  ✅ Xong! {elapsed:.1f}s ({done/elapsed:.1f} câu/s)")
    print(f"  💾 Đã lưu: {dst}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. food.csv — Đa luồng
# ══════════════════════════════════════════════════════════════════════════════
def _translate_food_batch(args):
    batch_idx, rows = args
    
    categories = [str(row.get("Category", "")) for row in rows]
    descriptions = [str(row.get("Description", "")) for row in rows]
    
    categories_vi = translate_batch(categories)
    descriptions_vi = translate_batch(descriptions)
    
    results = []
    for i, row in enumerate(rows):
        new_row = dict(row)
        new_row["Category_vi"] = categories_vi[i]
        new_row["Description_vi"] = descriptions_vi[i]
        results.append(new_row)
    
    return batch_idx, results


def translate_food_csv():
    src = os.path.join(DATASET_DIR, "food.csv")
    dst = os.path.join(DATASET_DIR, "food_bilingual.csv")

    print("\n" + "="*60)
    print("🥗 Dịch food.csv (GPU + Đa luồng)")
    print("="*60)

    _init_model()

    df = pd.read_csv(src)
    total = len(df)

    if os.path.exists(dst):
        done_df = pd.read_csv(dst)
        start = len(done_df)
        results_dict = {i: row for i, row in enumerate(done_df.to_dict("records"))}
        print(f"  ↩ Tiếp tục từ hàng {start}/{total}")
    else:
        results_dict = {}
        start = 0

    remaining = df.iloc[start:]
    
    # Chia batch
    batches = []
    for i in range(0, len(remaining), BATCH_SIZE):
        batch_df = remaining.iloc[i:i+BATCH_SIZE]
        batch_idx = start + i
        rows = batch_df.to_dict("records")
        batches.append((batch_idx, rows))
    
    print(f"  📦 Tổng {len(batches)} batches | {NUM_WORKERS_ACTIVE} workers\n")
    
    start_time = time.time()
    done = start
    
    with ThreadPoolExecutor(max_workers=NUM_WORKERS_ACTIVE) as executor:
        futures = {executor.submit(_translate_food_batch, batch): batch[0] for batch in batches}
        
        for future in as_completed(futures):
            batch_idx, batch_results = future.result()
            
            with _save_lock:
                for i, result in enumerate(batch_results):
                    results_dict[batch_idx + i] = result
                
                done = len(results_dict)
                elapsed = time.time() - start_time
                _print_progress(done, total, "🥗 Food", elapsed)
                
                if done % CHECKPOINT == 0 or done == total:
                    _flush_food(results_dict, total, dst, df.columns.tolist())

    _flush_food(results_dict, total, dst, df.columns.tolist())
    
    elapsed = time.time() - start_time
    print(f"\n  ✅ Xong! {elapsed:.1f}s ({done/elapsed:.1f} hàng/s)")
    print(f"  💾 Đã lưu: {dst}")


def _flush_food(results_dict, total, dst, orig_cols):
    ordered = [results_dict[i] for i in range(total) if i in results_dict]
    df_out = pd.DataFrame(ordered)
    cols_order = ["Category", "Category_vi", "Description", "Description_vi"] + \
                 [c for c in orig_cols if c not in ("Category", "Description")]
    final_cols = [c for c in cols_order if c in df_out.columns] + \
                 [c for c in df_out.columns if c not in cols_order]
    df_out[final_cols].to_csv(dst, index=False)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Gym xlsx — Đa luồng
# ══════════════════════════════════════════════════════════════════════════════
def _translate_gym_batch(args):
    batch_idx, rows, text_cols = args
    
    results = []
    for row in rows:
        translated = dict(row)
        for col in text_cols:
            val = row.get(col, "")
            if pd.notna(val) and val != "":
                translated[col + "_vi"] = translate_batch([str(val)])[0]
            else:
                translated[col + "_vi"] = ""
        results.append(translated)
    
    return batch_idx, results


def translate_gym_xlsx():
    src = os.path.join(DATASET_DIR, "Gym Exercises Dataset.xlsx")
    dst = os.path.join(DATASET_DIR, "Gym Exercises Dataset_bilingual.xlsx")

    print("\n" + "="*60)
    print("🏋️  Dịch Gym Exercises Dataset.xlsx (GPU + Đa luồng)")
    print("="*60)

    _init_model()

    df = pd.read_excel(src)
    text_cols = df.select_dtypes(include="object").columns.tolist()
    total = len(df)
    print(f"  Cột: {text_cols} | Hàng: {total}\n")

    # Chia batch
    batches = []
    for i in range(0, total, BATCH_SIZE):
        batch_df = df.iloc[i:i+BATCH_SIZE]
        rows = batch_df.to_dict("records")
        batches.append((i, rows, text_cols))
    
    results_dict = {}
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=NUM_WORKERS_ACTIVE) as executor:
        futures = {executor.submit(_translate_gym_batch, batch): batch[0] for batch in batches}
        
        for future in as_completed(futures):
            batch_idx, batch_results = future.result()
            
            with _save_lock:
                for i, result in enumerate(batch_results):
                    results_dict[batch_idx + i] = result
                
                done = len(results_dict)
                elapsed = time.time() - start_time
                _print_progress(done, total, "🏋️  Gym", elapsed)

    # Sắp xếp cột
    ordered = [results_dict[i] for i in range(total)]
    df_out = pd.DataFrame(ordered)
    final_cols = []
    for col in df.columns:
        final_cols.append(col)
        vi_col = col + "_vi"
        if vi_col in df_out.columns:
            final_cols.append(vi_col)

    df_out[final_cols].to_excel(dst, index=False)
    
    elapsed = time.time() - start_time
    print(f"\n  ✅ Xong! {elapsed:.1f}s")
    print(f"  💾 Đã lưu: {dst}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🚀 Dịch song ngữ SIÊU TỐC v2 (EN → VI) — GPU + Đa luồng tối ưu\n")

    args = sys.argv[1:]
    run_all = len(args) == 0

    if run_all or "med" in args:
        translate_medical_json()
    if run_all or "food" in args:
        translate_food_csv()
    if run_all or "gym" in args:
        translate_gym_xlsx()

    print("\n🎉 Hoàn tất!")
