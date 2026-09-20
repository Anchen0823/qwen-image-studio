@echo off
cd /d "%~dp0"
if not defined QWEN_MODEL_DIR set "QWEN_MODEL_DIR=D:\AI\Qwen-Image-2.1"
if not exist "%QWEN_MODEL_DIR%\.venv\Scripts\pythonw.exe" (
  echo Model Python environment not found. Check QWEN_MODEL_DIR.
  pause
  exit /b 1
)
start "" "%QWEN_MODEL_DIR%\.venv\Scripts\pythonw.exe" "%~dp0workbench.py"
