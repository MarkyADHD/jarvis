#Requires -Version 5.1
<#
  Post-install bootstrap for Jarvis. Handles what CAN be automated
  reliably (the Python venv + package install) and gives clear,
  copy-pasteable next steps for what can't (Claude Code login is
  interactive by design; backtalk's own installer is its own project
  and shouldn't be silently reimplemented here).
#>

$ErrorActionPreference = "Stop"
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
Say "  Core environment is ready. A few manual steps remain:"
Say "===================================================="
Say ""
Say "1. Voice pipeline (backtalk):" "White"
Say "   cd `"$root\backtalk`"" "Gray"
Say "   Follow backtalk\README.md / TROUBLESHOOTING.md for the Windows setup steps." "Gray"
Say ""
Say "2. Claude Code (Jarvis's brain) -- your OWN account, not the original owner's:" "White"
Say "   npm install -g @anthropic-ai/claude-code" "Gray"
Say "   claude login" "Gray"
Say ""
Say "3. Launch Jarvis:" "White"
Say "   $venvPath\Scripts\pythonw.exe `"$root\jarvis_app_v2.py`"" "Gray"
Say ""
Say "4. Add your own API keys / smart devices: click the gear icon in the" "White"
Say "   face HUD once Jarvis is running, or just tell him directly, e.g." "White"
Say "   'Jarvis, change my Spotify client ID.'" "White"
Say ""
Say "Full details are in FRIEND_SETUP.md in this same folder." "Cyan"
Say ""
Read-Host "Press Enter to close"
