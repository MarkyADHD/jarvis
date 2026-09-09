@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo   JARVIS -- pulling the latest updates from GitHub
echo ====================================================
echo.

git fetch origin main
if errorlevel 1 (
    echo Fetch failed -- check your internet connection.
    exit /b 1
)

git pull --ff-only origin main
if errorlevel 1 (
    echo Pull failed -- local changes may conflict with what's on GitHub.
    echo This needs a manual look at the repo, nothing was changed.
    exit /b 1
)

if exist "venv\Scripts\pip.exe" (
    echo.
    echo Checking for any new Python packages this update needs...
    "venv\Scripts\pip.exe" install -r requirements.txt --quiet
)

echo.
echo Update complete.
exit /b 0
