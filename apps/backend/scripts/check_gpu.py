#!/usr/bin/env python3
"""
Script kiểm tra GPU và PyTorch CUDA support
Chạy: python check_gpu.py
"""
import sys

def check_gpu():
    print("=" * 60)
    print("KIỂM TRA GPU VÀ PYTORCH CUDA SUPPORT")
    print("=" * 60)
    print()
    
    # 1. Kiểm tra PyTorch
    try:
        import torch
        print(f"✓ PyTorch version: {torch.__version__}")
        cuda_available = torch.cuda.is_available()
        print(f"{'✓' if cuda_available else '✗'} PyTorch CUDA available: {cuda_available}")
        
        if cuda_available:
            print(f"✓ CUDA version: {torch.version.cuda}")
            print(f"✓ Number of GPUs: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                gpu_name = torch.cuda.get_device_name(i)
                gpu_memory = torch.cuda.get_device_properties(i).total_memory / 1024**3
                print(f"  - GPU {i}: {gpu_name}")
                print(f"    Memory: {gpu_memory:.2f} GB")
        else:
            print("\n✗ CUDA not available - Backend sẽ chạy trên CPU")
            print("\nĐể sử dụng GPU, cần:")
            print("1. Cài đặt NVIDIA GPU driver (chạy: nvidia-smi)")
            print("2. Cài đặt CUDA Toolkit từ: https://developer.nvidia.com/cuda-downloads")
            print("3. Cài đặt PyTorch với CUDA support:")
            print("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
            print("\nHoặc chạy: install_pytorch_cuda.bat")
    except ImportError:
        print("✗ PyTorch chưa được cài đặt")
        print("Cài đặt: pip install torch")
        return False
    
    print()
    
    # 2. Kiểm tra sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer
        print(f"✓ sentence-transformers installed")
    except ImportError:
        print("✗ sentence-transformers chưa được cài đặt")
        print("Cài đặt: pip install sentence-transformers")
        return False
    
    print()
    
    # 3. Test embedding trên GPU
    if cuda_available:
        print("Testing embedding model on GPU...")
        try:
            model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cuda')
            embedding = model.encode("Test sentence", show_progress_bar=False)
            print(f"✓ Embedding test successful! Shape: {embedding.shape}")
            print(f"✓ Model is on device: {model.device}")
            print("\n✓ Backend sẽ tự động sử dụng GPU khi khởi động!")
        except Exception as e:
            print(f"✗ Error testing embedding: {e}")
            return False
    else:
        print("⚠ Backend sẽ chạy trên CPU (chậm hơn GPU 5-10x)")
    
    print()
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = check_gpu()
    sys.exit(0 if success else 1)
