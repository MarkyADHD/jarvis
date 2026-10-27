@echo off
rem Jarvis v3 (Electron). The Python Jarvis ("Launch Jarvis.bat") is untouched.
cd /d "%~dp0"
rem Launch log: shows whether the Startup shortcut fired and why Jarvis didn't come up.
if not exist "%APPDATA%\jarvis\data" mkdir "%APPDATA%\jarvis\data"
echo %date% %time% launch>> "%APPDATA%\jarvis\data\launch.log"
if not exist node_modules\electron\dist\electron.exe call npm install>> "%APPDATA%\jarvis\data\launch.log" 2>&1
start "" node_modules\electron\dist\electron.exe .>> "%APPDATA%\jarvis\data\launch.log" 2>&1
