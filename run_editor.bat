@echo off
REM KUKA GUI Editor Launcher for Windows
cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv venv
    echo Then run: venv\Scripts\activate
    echo Then run: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Activate virtual environment and run editor
call venv\Scripts\activate.bat
set MPLBACKEND=TkAgg
python kuka_gui_editor.py %*
