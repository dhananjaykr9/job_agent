@echo off
title AI Job Discovery Agent - Remove Auto-Start
echo ========================================================
echo   Removing Auto-Start
echo ========================================================
echo.

set SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AIJobDiscoveryAgent.lnk

if exist "%SHORTCUT_PATH%" (
    del "%SHORTCUT_PATH%"
    echo [SUCCESS] Auto-start removed successfully.
) else (
    echo Auto-start shortcut was not found.
)

echo.
pause
