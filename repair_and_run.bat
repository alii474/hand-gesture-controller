@echo off
echo ==========================================
echo    REPAIRING VIRTUAL ENVIRONMENT (STABLE MODE)
echo ==========================================

:: Check if .venv exists, if not create it
if not exist .venv (
    echo [1/3] Creating virtual environment...
    python -m venv .venv || py -m venv .venv
) else (
    echo [1/3] Virtual environment already exists.
)

echo [2/3] Installing dependencies with high stability...
echo (This uses a 1000s timeout to handle slow connections)

:: Use a longer timeout and no-cache to avoid corruption
.\.venv\Scripts\python.exe -m pip install --upgrade pip --timeout 1000
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --timeout 1000 --no-cache-dir

if %errorlevel% neq 0 (
    echo.
    echo [!] Installation interrupted. 
    echo [!] Trying one more time with a global mirror for better speed...
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 1000
)

echo ==========================================
echo    STARTING GESTURE CONTROLLER
echo ==========================================
.\.venv\Scripts\python.exe gesture_controller.py

pause
