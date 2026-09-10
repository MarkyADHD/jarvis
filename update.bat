@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo   JARVIS -- pulling the latest updates from GitHub
echo ====================================================
echo.

if not exist ".git" (
    echo This copy of Jarvis was installed from JarvisSetup.exe, not a git
    echo checkout -- there's no repository here for git to pull, so this
    echo script can't do anything on this install ^(that's expected, not
    echo an error in your setup^).
    echo.
    echo To update, either:
    echo   - Say "Jarvis, update yourself" -- he'll download and run the
    echo     latest installer automatically.
    echo   - Or grab the newest JarvisSetup.exe yourself from:
    echo     https://github.com/MarkyADHD/jarvis/releases/latest
    echo.
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
    echo Git isn't installed or isn't on PATH, so this script can't run
    echo git commands. This only matters on a real git checkout ^(the dev
    echo machine this repo lives on^) -- a normal install doesn't need git
    echo at all. Install Git for Windows from https://git-scm.com/download/win
    echo if you specifically want this script to work here.
    echo.
    exit /b 1
)

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
