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
    # A real user hit this window flashing open and closing instantly
    # with zero explanation. Root cause: Start-Process -Verb RunAs
    # THROWS if the UAC prompt is declined or can't be shown (not a
    # graceful failure) -- with $ErrorActionPreference=Stop and no
    # -NoExit, an uncaught exception here just kills the window before
    # anything gets a chance to print or pause. This is exactly why
    # nothing after this point in the whole script can be trusted to
    # run without its own safety net either -- see the try/finally
    # wrapping everything below.
    try {
        Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`"" -ErrorAction Stop
    } catch {
        Write-Host ""
        Write-Host "====================================================" -ForegroundColor Red
        Write-Host "  Administrator approval is required to continue." -ForegroundColor Red
        Write-Host "====================================================" -ForegroundColor Red
        Write-Host ""
        Write-Host "The Windows permission prompt was declined, or couldn't be shown." -ForegroundColor Yellow
        Write-Host "Run this again and click 'Yes' when Windows asks for permission." -ForegroundColor Yellow
        Write-Host ""
        Read-Host "Press Enter to close"
    }
    exit
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Everything else in this script runs inside one big try/finally so that
# ANY unexpected error -- not just the ones this script explicitly
# checks for with Fail() -- prints something and pauses instead of the
# window just vanishing, which is what actually happened to a real user
# and gave them zero information to act on.
try {

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
# Strict 3.12-only lookup -- deliberately separate from the unversioned
# fallback below. Earlier versions of this script folded both into one
# function that returned the FIRST thing it found, version 3.12 or not --
# which meant that on any machine that already had SOME Python on PATH
# (3.13, most commonly), the unversioned fallback always succeeded
# first, `$pyCmdParts[0]` was never null, and the winget-install-3.12
# step further down (gated on "nothing found at all") never ran. The
# script would then silently build a venv against 3.13 forever, no
# matter how many times it was re-run, hitting the same kokoro version
# conflict every single time. Splitting strict-3.12-only detection out
# means the caller can tell "no 3.12" apart from "no Python at all" and
# actually try to fix the former via winget instead of shrugging at it.
function Get-Python312Cmd {
    # `requirements.txt` was pinned against 3.12 -- some packages in it
    # may not have wheels built for newer Python versions yet, which
    # makes `pip install -r requirements.txt` fail on whichever package
    # hits that first and abort the WHOLE batch (a real report from a
    # real install: everything after that point, `requests` included,
    # silently never got installed). `py -3.12` asks the launcher for
    # that exact version if it's present, sidestepping the issue
    # instead of gambling on whatever "python"/"py" defaults to.
    # Redirecting a native command's stderr AT ALL -- 2>&1, or even
    # 2>$null -- combined with $ErrorActionPreference = "Stop" further
    # up this script, throws a terminating NativeCommandError in
    # PowerShell 5.1 the moment that command writes anything to stderr.
    # Confirmed the hard way (a real user's window died here) and then
    # confirmed again deliberately: `py -3.99 --version 2>$null` still
    # throws "No suitable Python runtime found" even though the error
    # text is being discarded, not merged -- it's the redirect itself
    # that triggers it, not what's done with the output. Verified the
    # actual fix too: no redirect at all, and the same failing command
    # just returns an empty result with no exception, which is exactly
    # the routine "not found" outcome this function needs to detect,
    # not treat as fatal.
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $v = & py -3.12 --version
            if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3\.12") { return @("py", "-3.12") }
        } catch { }
    }

    # `py -3.12` depends on Python having registered itself with the py
    # launcher's own version registry (PEP 514) -- a real install proved
    # this doesn't reliably happen for a SILENT winget install the way
    # it does for an interactive one from python.org. That left a 3.12
    # actually sitting on disk, installed successfully moments earlier
    # by this very script, completely invisible to `py -3.12` -- so the
    # script fell through to whatever unversioned "python" was on PATH
    # (3.13), and hit the exact kokoro Python-version conflict this
    # whole detection scheme exists to avoid. Checking the well-known
    # install locations directly sidesteps launcher registration
    # entirely for exactly this case.
    $directPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files (x86)\Python312\python.exe"
    )
    foreach ($path in $directPaths) {
        if (-not (Test-Path $path)) { continue }
        try {
            $v = & $path --version
            if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3\.12") { return @($path) }
        } catch { }
    }
    return $null
}

function Get-AnyPythonCmd {
    foreach ($candidate in @("py", "python")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            $v = & $candidate --version
            if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3\.") { return @($candidate) }
        } catch { }
    }
    return $null
}

$pyCmdParts = @(Get-Python312Cmd)
if (-not $pyCmdParts[0]) {
    # Strict 3.12 wasn't found -- try to actually get it via winget
    # BEFORE ever settling for whatever unversioned Python happens to
    # already be on PATH. Unlike Node.js/eSpeak NG below, Python used to
    # be a hard stop when missing entirely; now it also self-heals the
    # much more common case of "wrong version present", not just
    # "nothing present". Re-detect rather than trusting winget's own
    # exit code alone (winget can report success while PATH still needs
    # a fresh process to see it).
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Python 3.12 not found -- installing it via winget..."
        winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --silent
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        $pyCmdParts = @(Get-Python312Cmd)
    }
}
if (-not $pyCmdParts[0]) {
    # Genuinely couldn't get 3.12 (winget missing, blocked, offline,
    # etc.) -- fall back to whatever Python IS on PATH rather than
    # hard-failing, same as before. The warning right after this block
    # (pyVerLine -notmatch "Python 3\.12") already tells the user this
    # is a fallback, not confirmation everything will work.
    $pyCmdParts = @(Get-AnyPythonCmd)
}
if (-not $pyCmdParts[0]) {
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
try {
    $pyVerLine = (Invoke-Py --version) | Out-String
} catch {
    $pyVerLine = ""
}
Say "Found: $($pyVerLine.Trim())"
if ($pyVerLine -notmatch "Python 3\.12") {
    Write-Host "Warning: this is not Python 3.12, which is what requirements.txt was tested against." -ForegroundColor Yellow
    Write-Host "If package install fails below, installing Python 3.12 from https://python.org alongside your current version is the fix." -ForegroundColor Yellow
}

# --- venv ---
$venvPath = Join-Path $root "venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

# A venv from an earlier, failed run of THIS SAME script (built before
# the Python 3.12 detection above worked correctly) can already exist
# on disk, pinned to whatever wrong Python version was found back then
# (3.13+). "already exists, skip creation" used to trust that blindly --
# so even after fixing detection above, re-running the installer kept
# installing packages into the same stale, wrong-version venv and
# hitting the identical kokoro failure forever, no matter how good the
# detection got. Comparing the existing venv's actual Python version
# against what was just detected, and rebuilding if they don't match,
# is the only way a re-run can actually self-heal.
$needsRebuild = $false
if (Test-Path $venvPython) {
    try {
        $existingVer = & $venvPython --version
        if ($LASTEXITCODE -ne 0 -or "$existingVer" -notmatch "Python 3\.12") {
            Say "Existing virtual environment is on $existingVer, not 3.12 -- rebuilding it." "Yellow"
            $needsRebuild = $true
        }
    } catch {
        Say "Existing virtual environment's Python couldn't be checked -- rebuilding it." "Yellow"
        $needsRebuild = $true
    }
}

if ($needsRebuild) {
    Remove-Item -Recurse -Force $venvPath -ErrorAction SilentlyContinue
}

if (-not (Test-Path $venvPython)) {
    Say "Creating virtual environment..."
    Invoke-Py -m venv $venvPath
    if (-not (Test-Path $venvPython)) {
        Fail "Virtual environment creation failed -- $venvPython was never created. Check the output above for the real error."
    }
} else {
    Say "Virtual environment already exists and is on the right Python version, skipping creation."
}

$pip = Join-Path $venvPath "Scripts\pip.exe"
$reqFile = Join-Path $root "requirements.txt"

if (Test-Path $reqFile) {
    Say "Installing Python packages -- this downloads and builds ~200 packages" "Yellow"
    Say "including PyTorch and other large AI/ML libraries. It can genuinely" "Yellow"
    Say "take 10-20+ minutes depending on your internet speed and CPU." "Yellow"
    Say ""

    # pip streams live output fine during the download/collect phase, but
    # goes almost completely silent for MINUTES during the final
    # "Installing collected packages" unpack phase -- torch alone is a
    # 124 MB wheel to extract. A real user reported exactly this: no new
    # text for several minutes reads as a frozen window, and someone
    # without dev background has no reason to trust otherwise, so they
    # close it before it ever finishes.
    #
    # No output redirection at all -- UseShellExecute=$false with
    # RedirectStandard*=$false (the default) makes the child process
    # inherit this console's real output handle directly, so pip's own
    # text still streams to the screen completely normally and in real
    # time, exactly like `& $pip ...` does, with NO buffering/deadlock
    # risk (that risk only exists when actually redirecting stdout/
    # stderr, which needs the parent to actively pump the pipe or it can
    # fill up and stall the child -- deliberately avoided here). This
    # gets us one extra thing over plain `&`: a process handle to poll
    # from this same script while pip runs, so a heartbeat line can be
    # printed on top, independent of whatever pip itself is doing.
    #
    # Deliberately NOT using the Start-Process cmdlet with -PassThru for
    # this -- tested directly and confirmed its returned object's
    # ExitCode comes back $null even after WaitForExit(), which would
    # have made `$pipProc.ExitCode -ne 0` ALWAYS true ($null -ne 0 is
    # true in PowerShell) and reported every successful install as a
    # failure. Going straight to System.Diagnostics.Process, confirmed
    # working the same way, reads ExitCode correctly.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $pip
    $psi.Arguments = "install -r `"$reqFile`""
    $psi.UseShellExecute = $false
    $pipProc = [System.Diagnostics.Process]::Start($psi)
    $pipStart = Get-Date
    while (-not $pipProc.WaitForExit(20000)) {
        $elapsedMin = [Math]::Round(((Get-Date) - $pipStart).TotalMinutes, 1)
        Write-Host "   ...still working ($elapsedMin min elapsed) -- long quiet stretches here are normal, not a freeze. Please keep this window open." -ForegroundColor DarkGray
    }
    if ($pipProc.ExitCode -ne 0) {
        Fail "pip install failed (exit code $($pipProc.ExitCode)) -- see the pip output above for the real reason. Common causes: no internet connection, or a firewall/antivirus blocking pip. Fix that, then run this script again."
    }
    # pip can exit 0 while still not actually having installed everything
    # in rare partial-failure cases -- a real import check is the only way
    # to be sure the environment actually works, not just that pip ran.
    # No stderr redirect here on purpose -- see the note above
    # Get-RealPythonCmd about why that throws instead of just failing.
    # This exact line would otherwise crash the moment `import requests`
    # legitimately fails, which is precisely the case it exists to catch.
    try {
        & $venvPython -c "import requests"
        $importOk = ($LASTEXITCODE -eq 0)
    } catch {
        $importOk = $false
    }
    if (-not $importOk) {
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
Say "  Tailscale -- optional, for talking to Jarvis remotely"
Say "===================================================="
Say ""

# Purely optional (unlike eSpeak NG above) -- Jarvis's remote-chat
# server already runs fine without it, just LAN-only. Tailscale is what
# makes "http://<tailscale-ip>:8792" reachable from your phone anywhere,
# not just at home. Best-effort and silent about failure on purpose:
# nothing else in Jarvis depends on this succeeding.
$tailscaleExe = @(
    "C:\Program Files\Tailscale\tailscale.exe",
    "C:\Program Files (x86)\Tailscale\tailscale.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($tailscaleExe) {
    Say "Found: $tailscaleExe"
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Tailscale not found -- installing via winget..."
        winget install --id tailscale.tailscale -e --accept-source-agreements --accept-package-agreements --silent
        $tailscaleExe = @(
            "C:\Program Files\Tailscale\tailscale.exe",
            "C:\Program Files (x86)\Tailscale\tailscale.exe"
        ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if ($tailscaleExe) {
        Say "Installed: $tailscaleExe"
        Say "One-time steps whenever you want remote access: open a terminal and run 'tailscale up' -- it opens a browser to sign in. Then tell Jarvis 'set up remote https' once (needed for your phone's microphone to work on the page -- plain http:// URLs get blocked from using the mic by the browser itself). After that, ask Jarvis 'what's my remote address' for the URL to use from your phone." "White"
    } else {
        Write-Host "Tailscale could not be installed automatically -- skipping, this is optional." -ForegroundColor Yellow
        Write-Host "Install it yourself later if you want remote access: https://tailscale.com/download (or 'winget install tailscale.tailscale')" -ForegroundColor Yellow
    }
}

Say ""
Say "===================================================="
Say "  JarvisVision -- optional, lets Jarvis see your screen"
Say "===================================================="
Say ""

# Optional, same reasoning as Tailscale above -- Jarvis's Claude-backed
# conversation works fine without this. But without Ollama and its
# vision model installed, "what's on my screen" / JarvisVision silently
# failed on every install except the dev machine (which already had
# both by hand) -- confirmed nothing in this script ever installed
# either one. qwen2.5vl:7b is a real download (a few GB); best-effort
# and non-fatal on purpose, same as Tailscale.
$ollamaExe = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaExe) {
    Say "Found: $($ollamaExe.Source)"
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Ollama not found -- installing via winget..."
        winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements --silent
        $ollamaExe = Get-Command ollama -ErrorAction SilentlyContinue
    }
}

if ($ollamaExe) {
    Say "Pulling the JarvisVision model (qwen2.5vl:7b) -- this is a real download, please be patient..."
    try {
        & $ollamaExe.Source pull qwen2.5vl:7b
        Say "JarvisVision is ready. Ask Jarvis things like 'what's on my screen' any time."
    } catch {
        Write-Host "Could not pull the JarvisVision model automatically -- skipping, this is optional." -ForegroundColor Yellow
        Write-Host "Install it yourself later by running 'ollama pull qwen2.5vl:7b'." -ForegroundColor Yellow
    }
} else {
    Write-Host "Ollama could not be installed automatically -- skipping, this is optional." -ForegroundColor Yellow
    Write-Host "JarvisVision ('what's on my screen') needs it -- install yourself later: https://ollama.com/download (or 'winget install Ollama.Ollama'), then run 'ollama pull qwen2.5vl:7b'." -ForegroundColor Yellow
}

Say ""
Say "===================================================="
Say "  FFmpeg -- audio/video for the mobile voice page and clipping"
Say "===================================================="
Say ""

# Optional, same reasoning as Tailscale/Ollama above. Confirmed this was
# NEVER installed by this script -- it only worked on the dev machine
# because ffmpeg happened to already be there from something unrelated.
# Without it: the mobile HUD's voice page can't decode a phone's
# recording, and JarvisClipper (VOD highlight clipping) can't read or
# cut any video at all.
$ffmpegExe = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpegExe) {
    Say "Found: $($ffmpegExe.Source)"
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "FFmpeg not found -- installing via winget..."
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
        $ffmpegExe = Get-Command ffmpeg -ErrorAction SilentlyContinue
    }
    if ($ffmpegExe) {
        Say "Installed: $($ffmpegExe.Source)"
    } else {
        Write-Host "FFmpeg could not be installed automatically -- skipping, this is optional." -ForegroundColor Yellow
        Write-Host "The mobile voice page and JarvisClipper need it -- install yourself later: https://www.gyan.dev/ffmpeg/builds/ (or 'winget install Gyan.FFmpeg'), then open a NEW terminal so PATH updates." -ForegroundColor Yellow
    }
}

Say ""
Say "===================================================="
Say "  Claude Code -- optional, Jarvis's preferred brain"
Say "===================================================="
Say ""

# Claude Code used to be a hard requirement here (forced Node.js install,
# forced npm install, forced blocking `claude login`). It no longer is --
# Jarvis now has a real provider router (jarvis_provider_router_v1.py)
# that falls back to the free local Ollama brain (already installed a
# few steps up for JarvisVision, same qwen2.5vl:7b model) whenever Claude
# Code isn't found, with zero action needed from anyone. So this whole
# section is now best-effort and non-fatal, same pattern as Tailscale/
# Ollama/FFmpeg above -- nothing after this point depends on it
# succeeding. Existing users who already have Claude Code installed and
# logged in see no change at all: the router still defaults to Claude
# whenever it's actually present.
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Node.js not found -- installing via winget (needed for Claude Code and other AI providers)..."
        winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements --silent
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        $npm = Get-Command npm -ErrorAction SilentlyContinue
    }
}

if (-not $npm) {
    Write-Host "Node.js could not be installed automatically -- skipping Claude Code, this is optional." -ForegroundColor Yellow
    Write-Host "Jarvis will run on the free local AI brain instead. Install Node.js yourself later if you want Claude: https://nodejs.org" -ForegroundColor Yellow
} else {
    Say "Found: npm $(& npm --version)"

    $claude = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $claude) {
        Say "Installing Claude Code..."
        try {
            & npm install -g @anthropic-ai/claude-code
        } catch { }
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        $claude = Get-Command claude -ErrorAction SilentlyContinue
    }

    if (-not $claude) {
        Write-Host "Claude Code install didn't complete -- skipping, this is optional." -ForegroundColor Yellow
        Write-Host "Jarvis will run on the free local AI brain instead. Install it yourself later: 'npm install -g @anthropic-ai/claude-code', then 'claude login', or just tell Jarvis 'switch to claude' once it's installed." -ForegroundColor Yellow
    } else {
        Say "Claude Code installed."

        # Heuristic for "already logged in": Claude Code's own credential
        # file in the user profile, entirely separate from this project
        # folder -- the same reason the original owner's login could
        # never have shipped with this copy in the first place.
        $credFile = Join-Path $env:USERPROFILE ".claude\.credentials.json"
        if (Test-Path $credFile) {
            Say "Claude Code already has a login on this machine -- skipping." "Green"
        } else {
            Say ""
            Say "Optional: sign in now with YOUR OWN Claude account (not the" "White"
            Say "original owner's -- this is separate per-machine, per-user login)" "White"
            Say "if you want Claude as your brain. You can skip this and Jarvis" "White"
            Say "will use the free local AI brain instead -- sign in any time" "White"
            Say "later by telling Jarvis 'switch to claude'." "White"
            Say ""
            $signInChoice = Read-Host "Sign in to Claude now? (y/N)"
            if ($signInChoice.Trim().ToUpper() -eq "Y") {
                & claude login
            } else {
                Say "Skipped -- Jarvis will use the free local AI brain for now." "Gray"
            }
        }
    }
}

Say ""
Say "===================================================="
Say "  All done -- everything Jarvis needs is installed."
Say "===================================================="
Say ""

# Launch Jarvis for real, here, rather than as a separate installer
# checkbox someone could tick independently of "Finish setup" -- that
# earlier design let a real user uncheck Finish Setup but leave Launch
# checked, producing "Unable to execute pythonw.exe: the system cannot
# find the file specified" since the venv didn't exist yet. This point
# in the script is the one place the venv's existence is guaranteed,
# not assumed.
#
# This whole script is running elevated (self-elevated at the top), but
# Jarvis itself should NOT run as admin -- launching it directly here
# would inherit that. The standard de-elevation trick: hand a shortcut
# to explorer.exe, which always runs at the logged-in user's own normal
# integrity level regardless of what elevated process asked it to.
Say "Launching Jarvis now..." "Green"
try {
    $tempLnk = Join-Path $env:TEMP "LaunchJarvis.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $sc = $wsh.CreateShortcut($tempLnk)
    $sc.TargetPath = $venvPython.Replace("python.exe", "pythonw.exe")
    $sc.Arguments = """$root\jarvis_app_v2.py"""
    $sc.WorkingDirectory = $root
    $sc.Save()
    Start-Process "explorer.exe" -ArgumentList "`"$tempLnk`""
} catch {
    Write-Host "Couldn't auto-launch Jarvis -- start him from the Desktop/Start Menu shortcut instead." -ForegroundColor Yellow
}

Say ""
Say "(or just use the JARVIS shortcut on your Desktop / Start Menu next time)" "Gray"
Say ""
Say "Add your own API keys / smart devices: click the gear icon in the" "White"
Say "face HUD once Jarvis is running, or just tell him directly, e.g." "White"
Say "'Jarvis, change my Spotify client ID.'" "White"
Say ""
Say "Full details are in FRIEND_SETUP.md in this same folder." "Cyan"
Say ""
Read-Host "Press Enter to close"

} catch {
    # Catches anything NOT already handled by this script's own Fail()
    # calls (those already print their own message and exit cleanly,
    # which does not trigger this catch) -- this is the safety net for
    # a genuinely unexpected error anywhere in the script, so the window
    # always shows something and waits instead of silently vanishing.
    Write-Host ""
    Write-Host "====================================================" -ForegroundColor Red
    Write-Host "  Something went wrong that this script didn't expect:" -ForegroundColor Red
    Write-Host "====================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Full details, for reporting this:" -ForegroundColor Gray
    Write-Host ($_ | Out-String) -ForegroundColor Gray
    Write-Host ""
    Read-Host "Press Enter to close"
}
