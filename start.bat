@echo off
rem Starts the app: creates the virtual environment the first time, installs requirements, opens the UI.
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3 -m venv venv 2>nul || python -m venv venv
    if not exist "venv\Scripts\python.exe" (
        echo Python 3 was not found. Install it from https://www.python.org and run this file again.
        pause
        exit /b 1
    )
)

echo Checking requirements...
"venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Installing the requirements failed.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" -m streamlit run ui.py
pause
