#Requires -Version 5.1
<#
  Post-install bootstrap for Jarvis. Handles what CAN be automated
  reliably (the Python venv + package install, Node.js + Claude Code
  install via winget/npm, and launching `claude login` itself) and
  gives clear, copy-pasteable next steps for the one thing that
  genuinely can't be scripted around: backtalk's own voice-pipeline
  installer is its own separate project and shouldn't be silently
  reimplemented here.
#>

$ErrorActionPreference = "Stop"

# Self-elevate if not already running as admin. The installer itself
# runs elevated (creating C:\AI-Agent under an admin-owned ACL), but
# this script can be launched two different ways afterward: the
# installer's own "run now" prompt (already elevated, inherits it) or
# the "Finish Setup" Start Menu shortcut launched later on its own
# (NOT elevated by default). That second path could fail to write into
# the venv or install packages with no visible error beyond a vague
# permissions failure -- which is exactly what produced a venv that
# looked like it worked but was actually missing packages, including
# `requests`, one of the most basic ones. Self-elevating here removes
# the ambiguity regardless of which way this got launched.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    exit
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Say($text, $color = "Cyan") { Write-Host $text -ForegroundColor $color }

Say ""
Say "===================================================="
Say "  JARVIS -- environment setup"
Say "===================================================="
Say ""

# --- Python check ---
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python was not found on PATH." -ForegroundColor Red
    Write-Host "Install Python 3.12 from https://python.org (check 'Add to PATH' during install), then run this script again." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}
$verLine = (& python --version) 2>&1
Say "Found: $verLine"

# --- venv ---
$venvPath = Join-Path $root "venv"
if (-not (Test-Path $venvPath)) {
    Say "Creating virtual environment..."
    & python -m venv $venvPath
} else {
    Say "Virtual environment already exists, skipping creation."
}

$pip = Join-Path $venvPath "Scripts\pip.exe"
$reqFile = Join-Path $root "requirements.txt"

if (Test-Path $reqFile) {
    Say "Installing Python packages (this can take several minutes)..."
    & $pip install -r $reqFile
} else {
    Write-Host "requirements.txt not found -- skipping package install." -ForegroundColor Yellow
}

Say ""
Say "===================================================="
Say "  Claude Code -- Jarvis's brain"
Say "===================================================="
Say ""

# --- Node.js check (needed for npm, needed for Claude Code) ---
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Node.js not found -- installing via winget (needed for Claude Code)..."
        winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements --silent
        # winget just changed PATH machine/user-wide; this process's own
        # PATH won't see it until refreshed from the registry.
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        $npm = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $npm) {
        Write-Host "Node.js is required for Claude Code and could not be installed automatically." -ForegroundColor Red
        Write-Host "Install it from https://nodejs.org (LTS version), then run this script again." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit 1
    }
}
Say "Found: npm $(& npm --version)"

# --- Claude Code CLI ---
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
    Say "Installing Claude Code..."
    & npm install -g @anthropic-ai/claude-code
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    $claude = Get-Command claude -ErrorAction SilentlyContinue
}

if (-not $claude) {
    Write-Host "Claude Code install didn't complete -- run 'npm install -g @anthropic-ai/claude-code' yourself, then 'claude login'." -ForegroundColor Red
} else {
    Say "Claude Code installed."

    # Heuristic for "already logged in": Claude Code's own credential
    # file in the user profile, entirely separate from this project
    # folder -- the same reason the original owner's login could never
    # have shipped with this copy in the first place.
    $credFile = Join-Path $env:USERPROFILE ".claude\.credentials.json"
    if (Test-Path $credFile) {
        Say "Claude Code already has a login on this machine -- skipping." "Green"
    } else {
        Say ""
        Say "One more step: sign in with YOUR OWN Claude account (not the" "White"
        Say "original owner's -- this is separate per-machine, per-user login)." "White"
        Say "This opens your browser for a normal Claude/Anthropic sign-in." "White"
        Say ""
        & claude login
    }
}

Say ""
Say "===================================================="
Say "  Almost done -- one manual step remains:"
Say "===================================================="
Say ""
Say "Voice pipeline (backtalk):" "White"
Say "   cd `"$root\backtalk`"" "Gray"
Say "   Follow backtalk\README.md / TROUBLESHOOTING.md for the Windows setup steps." "Gray"
Say ""
Say "Then launch Jarvis:" "White"
Say "   $venvPath\Scripts\pythonw.exe `"$root\jarvis_app_v2.py`"" "Gray"
Say "   (or just use the JARVIS shortcut on your Desktop / Start Menu)" "Gray"
Say ""
Say "Add your own API keys / smart devices: click the gear icon in the" "White"
Say "face HUD once Jarvis is running, or just tell him directly, e.g." "White"
Say "'Jarvis, change my Spotify client ID.'" "White"
Say ""
Say "Full details are in FRIEND_SETUP.md in this same folder." "Cyan"
Say ""
Read-Host "Press Enter to close"
