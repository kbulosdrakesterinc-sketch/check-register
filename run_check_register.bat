@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    echo Python 3 was not found on this computer.
    echo Install Python 3.12 or newer, then run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating local Python environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto error
    set "PYTHON_CMD=.venv\Scripts\python.exe"
)

echo Installing required packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo Starting Check Register...
".venv\Scripts\python.exe" -m check_register
if errorlevel 1 goto error

exit /b 0

:error
echo.
echo Check Register could not start. Review the error above.
pause
exit /b 1
