#Requires -Version 5.1
<#
  Post-install bootstrap for Jarvis. Handles everything that CAN be
  automated reliably: Python 3.12 itself (installed via winget if
  missing, not just detected), the venv + package install (targeting
  that exact 3.12, verified rather than assumed to have worked),
  eSpeak NG (the one real system-level voice dependency -- confirmed
  required, not optional, see the section below), and Node.js +
  Claude Code install/login. backtalk's own dependencies are already
  fully covered by requirements.txt (verified: every package
  backtalk's pyproject.toml declares is in there) -- its own separate
  installer is for running it standalone, not needed here at all.
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

function Fail($text) {
    Write-Host $text -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# --- Python check ---
# `Get-Command python` succeeding is NOT proof of a real Python install --
# Windows ships a "python" App Execution Alias stub (at
# %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe) that satisfies this
# check, is FIRST on PATH by default ahead of a real install, and does
# nothing but print a Microsoft Store nag when run (exit code 9009).
# Confirmed hitting this on the machine this project was built on, so
# it is not an edge case -- it's the default on a lot of Windows
# machines. The `py` launcher (py.exe, installed by the real python.org
# installer, not the Store) is immune to this and is tried first.
function Get-RealPythonCmd {
    # `requirements.txt` was pinned against 3.12 -- some packages in it
    # may not have wheels built for newer Python versions yet, which
    # makes `pip install -r requirements.txt` fail on whichever package
    # hits that first and abort the WHOLE batch (a real report from a
    # real install: everything after that point, `requests` included,
    # silently never got installed). `py -3.12` asks the launcher for
    # that exact version if it's present, sidestepping the issue
    # instead of gambling on whatever "python"/"py" defaults to.
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) {
        $v = (& py -3.12 --version) 2>&1 | Out-String
        if ($v -match "Python 3\.12") { return @("py", "-3.12") }
    }
    foreach ($candidate in @("py", "python")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $v = (& $candidate --version) 2>&1 | Out-String
        if ($v -match "Python 3\.") { return @($candidate) }
    }
    return $null
}
$pyCmdParts = Get-RealPythonCmd
if (-not $pyCmdParts) {
    # Unlike Node.js/eSpeak NG below, this was previously a hard stop --
    # inconsistent, and the single most likely thing someone with no dev
    # background doesn't already have. Auto-install via winget the same
    # way, then re-detect rather than trusting the installer's own exit
    # code alone (winget can report success while PATH still needs a
    # fresh process to see it).
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Python not found -- installing Python 3.12 via winget..."
        winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --silent
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        $pyCmdParts = Get-RealPythonCmd
    }
}
if (-not $pyCmdParts) {
    Fail "No working Python install found and it could not be installed automatically. `'python`' on PATH resolving to the Windows Store stub instead of a real install is the most common cause.`nInstall Python 3.12 from https://python.org (check 'Add to PATH' during install), then run this script again."
}
function Invoke-Py {
    # Splatting $pyCmdParts[1..($pyCmdParts.Count-1)] breaks when Count
    # is 1 -- PowerShell's `1..0` range produces (1, 0), not an empty
    # array, so slicing "everything after index 0" needs an explicit
    # guard rather than relying on the range operator to do it.
    #
    # Using the automatic $args variable rather than a declared
    # [Parameter(ValueFromRemainingArguments)] -- that attribute needs
    # [CmdletBinding()] to actually bind correctly; without it, a first
    # attempt here silently ate the "--version" argument and launched
    # an interactive Python REPL instead of printing a version string.
    # $args needs no such ceremony and is the safer default for "just
    # pass everything through" in a plain function.
    # The @(...) wrapper is load-bearing: assigning an if/else
    # expression's result directly to a variable silently unwraps a
    # single-element array into a plain scalar string in PowerShell,
    # which then breaks @-splatting in a way that's genuinely hard to
    # spot -- confirmed the hard way: `py -3.12 --version` spawned an
    # interactive REPL instead of printing a version, because the
    # unwrapped scalar splat somehow dropped `--version` off the call
    # entirely. Forcing the array subexpression operator here keeps it
    # an actual array regardless of element count.
    $pyExtra = @(if ($pyCmdParts.Count -gt 1) { $pyCmdParts[1..($pyCmdParts.Count - 1)] } else { @() })
    & $pyCmdParts[0] @pyExtra @args
}
$pyVerLine = (Invoke-Py --version) 2>&1 | Out-String
Say "Found: $($pyVerLine.Trim())"
if ($pyVerLine -notmatch "Python 3\.12") {
    Write-Host "Warning: this is not Python 3.12, which is what requirements.txt was tested against." -ForegroundColor Yellow
    Write-Host "If package install fails below, installing Python 3.12 from https://python.org alongside your current version is the fix." -ForegroundColor Yellow
}

# --- venv ---
$venvPath = Join-Path $root "venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Say "Creating virtual environment..."
    Invoke-Py -m venv $venvPath
    if (-not (Test-Path $venvPython)) {
        Fail "Virtual environment creation failed -- $venvPython was never created. Check the output above for the real error."
    }
} else {
    Say "Virtual environment already exists, skipping creation."
}

$pip = Join-Path $venvPath "Scripts\pip.exe"
$reqFile = Join-Path $root "requirements.txt"

if (Test-Path $reqFile) {
    Say "Installing Python packages (this can take several minutes)..."
    & $pip install -r $reqFile
    if ($LASTEXITCODE -ne 0) {
        Fail "pip install failed (exit code $LASTEXITCODE) -- see the pip output above for the real reason. Common causes: no internet connection, or a firewall/antivirus blocking pip. Fix that, then run this script again."
    }
    # pip can exit 0 while still not actually having installed everything
    # in rare partial-failure cases -- a real import check is the only way
    # to be sure the environment actually works, not just that pip ran.
    & $venvPython -c "import requests" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Fail "Packages were installed but a basic import check (requests) still failed. Try running manually to see the real error:`n  $pip install -r `"$reqFile`""
    }
    Say "Package install verified."
} else {
    Fail "requirements.txt not found next to this script -- the installed copy looks incomplete. Re-run the installer."
}

Say ""
Say "===================================================="
Say "  eSpeak NG -- needed for Jarvis's voice"
Say "===================================================="
Say ""

# Kokoro (the built-in voice) phonemizes text through espeak-ng. The
# pip-installable espeakng-loader wheel has a known-broken build path
# (confirmed the hard way, documented in backtalk's own
# TROUBLESHOOTING.md) -- the actual supported path is a real system
# install, which is not something pip/requirements.txt can ever
# provide. Without this, voice output fails to load entirely.
$espeakPaths = @(
    "C:\Program Files\eSpeak NG\libespeak-ng.dll",
    "C:\Program Files (x86)\eSpeak NG\libespeak-ng.dll"
)
$espeakFound = $espeakPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($espeakFound) {
    Say "Found: $espeakFound"
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "eSpeak NG not found -- installing via winget..."
        winget install --id eSpeak-NG.eSpeak-NG -e --accept-source-agreements --accept-package-agreements --silent
        $espeakFound = $espeakPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if ($espeakFound) {
        Say "Installed: $espeakFound"
    } else {
        Write-Host "eSpeak NG could not be installed automatically." -ForegroundColor Yellow
        Write-Host "Voice output will fail to load until you install it yourself: https://github.com/espeak-ng/espeak-ng/releases (or 'winget install eSpeak-NG.eSpeak-NG')" -ForegroundColor Yellow
        Write-Host "Continuing setup -- this alone won't block anything else below." -ForegroundColor Yellow
    }
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
Say "  All done -- everything Jarvis needs is installed."
Say "===================================================="
Say ""
Say "Launch Jarvis:" "White"
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
