@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  VoiceType - Windows x64 Build Script
echo ========================================
echo.

:: Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add to PATH.
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] Python version: %PYVER%

:: Check PyInstaller
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller not installed, installing now...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

:: Install project dependencies
echo [INFO] Installing project dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [INFO] Building VoiceType EXE...
echo.

pyinstaller --clean --name="VoiceType" ^
    --windowed ^
    --noconfirm ^
    --onefile ^
    --collect-all PySide6 ^
    voice_type/__main__.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build successful!
echo  Output: dist\VoiceType.exe
echo ========================================
pause
