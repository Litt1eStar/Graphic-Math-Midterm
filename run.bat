@echo off
setlocal
cd /d "%~dp0"
if exist "S13-30612.exe" (
    "S13-30612.exe"
    if errorlevel 1 pause
    exit /b
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" classroom.py
    if errorlevel 1 pause
    exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 classroom.py
) else (
    python classroom.py
)
if errorlevel 1 pause
