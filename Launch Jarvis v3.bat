@echo off
rem Jarvis v3 (Electron). The Python Jarvis ("Launch Jarvis.bat") is untouched.
cd /d "%~dp0"
if not exist node_modules\electron\dist\electron.exe call npm install
start "" node_modules\electron\dist\electron.exe .
