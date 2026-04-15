@echo off
echo ========================================
echo  RAGBot Setup
echo ========================================

:: Tạo venv
if not exist "venv" python -m venv venv
call venv\Scripts\activate.bat

pip install --upgrade pip -q
pip install -r requirements.txt -q

echo.
echo ========================================
echo  Cai Ollama va model
echo ========================================
echo 1. Tai Ollama: https://ollama.com/download
echo 2. Sau khi cai xong, chay:
echo    ollama pull llama3
echo    (hoac: ollama pull mistral  neu RAM it hon 8GB)
echo.
echo ========================================
echo  Chay RAGBot
echo ========================================
echo Buoc 1 - Ingest data:
echo    python ingest.py --limit 50000
echo.
echo Buoc 2 - Chay API server:
echo    python api.py
echo.
echo API docs: http://localhost:8000/docs
pause
