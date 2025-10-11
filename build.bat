@echo off
REM Automated build script for KUKA Editor Windows executable
REM This script handles environment setup and building

echo ========================================
echo  KUKA Editor - Windows Build Script
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.11+ from python.org
    pause
    exit /b 1
)

echo [1/5] Checking virtual environment...
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created.
) else (
    echo Virtual environment already exists.
)

echo.
echo [2/5] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)

echo.
echo [3/5] Installing/updating dependencies...
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [4/5] Building executable (this may take 2-5 minutes)...
pyinstaller --clean --noconfirm build_windows.spec
if errorlevel 1 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo.
echo [5/5] Build complete!
echo ========================================
echo.
echo Executable created at: dist\KUKAEditor.exe
echo.
echo File info:
dir dist\KUKAEditor.exe | find "KUKAEditor.exe"
echo.
echo ========================================
echo  Build successful!
echo ========================================
echo.
echo Next steps:
echo   1. Test: dist\KUKAEditor.exe
echo   2. Distribute the .exe file
echo.
echo The .exe is standalone - no Python needed!
echo.
pause
