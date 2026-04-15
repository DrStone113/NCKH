"""
chat.py — Chat trực tiếp trên terminal (không cần API server)
Sử dụng: python chat.py
"""

from rag import RAGBot

def main():
    print("=" * 50)
    print("  RAGBot Medical Chat")
    print("  Gõ 'quit' hoặc 'exit' để thoát")
    print("=" * 50 + "\n")

    bot = RAGBot()

    while True:
        try:
            question = input("Bạn: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nTạm biệt!")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "thoat"):
            print("Tạm biệt!")
            break

        print("\nBot: ", end="", flush=True)
        for chunk in bot.stream(question):
            print(chunk, end="", flush=True)
        print("\n")

if __name__ == "__main__":
    main()
