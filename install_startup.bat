@echo off
title AI Job Discovery Agent - Auto-Start Setup
echo ========================================================
echo   Setting up Auto-Start on Windows Boot
echo ========================================================
echo.

set SCRIPT_DIR=%~dp0
set VBS_TARGET=%SCRIPT_DIR%start_background.vbs
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT_PATH=%STARTUP_DIR%\AIJobDiscoveryAgent.lnk

echo Creating shortcut in Windows Startup folder...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_TARGET%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.WindowStyle = 7; $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo.
    echo [SUCCESS] Auto-start installed!
    echo The agent will now start automatically whenever your laptop boots.
    echo It runs silently in the background and searches every hour.
    echo.
    echo To verify logs anytime, check: %SCRIPT_DIR%logs\
) else (
    echo.
    echo [ERROR] Could not create startup shortcut.
)

echo.
pause
