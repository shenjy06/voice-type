@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  VoiceType - Clean Build Artifacts
echo ========================================
echo.

set "ROOT=%~dp0"
set "REMOVED=0"

call :clean_dir "build\VoiceType"
call :clean_dir "dist"
call :clean_dir ".pytest_cache"
call :clean_dir "voice_type.egg-info"

call :clean_pycache "voicetype"
call :clean_pycache "tests"
call :clean_pycache "voicetype\ui"
call :clean_pycache "tests\ui"

echo.
echo ========================================
echo  Clean complete (%REMOVED% items removed)
echo ========================================
pause
exit /b 0

:clean_dir
set "target=%ROOT%~1"
if exist "%target%" (
    echo [DEL] %~1
    rmdir /s /q "%target%" 2>nul
    set /a REMOVED+=1
)
exit /b 0

:clean_pycache
set "target=%ROOT%~1\__pycache__"
if exist "%target%" (
    echo [DEL] %~1\__pycache__
    rmdir /s /q "%target%" 2>nul
    set /a REMOVED+=1
)
exit /b 0
