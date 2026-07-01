@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  VoiceType - Windows x64 Build Script
echo ========================================
echo.

:: Locate the virtual environment
set "VENV=.venv"
if not exist "%VENV%\Scripts\python.exe" (
    echo [INFO] Virtual environment not found, creating now...
    python -m venv %VENV%
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "PYTHON=%VENV%\Scripts\python.exe"
set "PIP=%VENV%\Scripts\pip.exe"
set "PYINSTALLER=%VENV%\Scripts\pyinstaller.exe"

:: Check Python version
for /f "tokens=2" %%i in ('"%PYTHON%" --version 2^>^&1') do set PYVER=%%i
echo [OK] Python version: %PYVER% ^(from %VENV%^)

:: Check PyInstaller
"%PYTHON%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller not installed, installing now...
    "%PIP%" install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

:: Install project dependencies
echo [INFO] Installing project dependencies...
"%PIP%" install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Install the project itself so entry points / metadata are present
echo [INFO] Installing project in editable mode...
"%PIP%" install -e .
if errorlevel 1 (
    echo [ERROR] Failed to install project.
    pause
    exit /b 1
)

echo.
echo [INFO] Building VoiceType EXE...
echo.

"%PYINSTALLER%" --clean ^
    --noconfirm ^
    VoiceType.spec

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
