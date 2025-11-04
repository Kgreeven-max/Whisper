@echo off
REM Meeting Transcriber - Windows Installation Script

echo ============================================================
echo Meeting Transcriber - Windows Installation
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

echo Installing dependencies...
echo.

REM Install base requirements
pip install --upgrade pip
pip install -r requirements.txt

REM Install Windows-specific packages
echo Installing Windows-specific packages...
pip install pywin32

echo.
echo ============================================================
echo Installation Complete!
echo ============================================================
echo.
echo Next steps:
echo 1. Run: python meeting_monitor.py
echo 2. The app will appear in your system tray
echo 3. Open Teams and join a meeting
echo 4. The app will prompt you to transcribe automatically!
echo.
echo Optional - Calendar Integration:
echo For Google Calendar: Place google_credentials.json in:
echo   %USERPROFILE%\.meeting-transcriber\
echo.
echo For Outlook/Teams Calendar: Set environment variable:
echo   set MS_CLIENT_ID=your_client_id
echo.
pause
