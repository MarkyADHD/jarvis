<#
.SYNOPSIS
  Exports a clean, shareable copy of Jarvis with your memory, secrets,
  and dev-history clutter stripped out -- for a friend to set up as
  their own instance with their own Claude Code login and API keys.

.DESCRIPTION
  Run this FROM C:\AI-Agent. It copies the project to a new folder
  (default: C:\JarvisExport) using robocopy with an exclude list for
  everything personal or machine-specific:

    - Your memory (JarvisMemory\, the settings/secrets store)
    - Your remote-chat access token (regenerates itself on first run)
    - Your own venvs (yours has absolute paths baked in -- your friend
      builds his own from requirements.txt / backtalk's own installer)
    - Historical backup/installer-payload folders and *_backup_*.py
      files that were snapshots of past self-edits, not live code
    - __pycache__, build/, dist/ (generated, PyInstaller leftovers)
    - Your Edge browser profile for the HUD window

  It does NOT touch C:\AI-Agent itself -- everything happens in the
  destination copy. After copying, it runs sanitize_friend_edition.py
  against the COPY ONLY to strip your name and reset the file-access
  scope in CLAUDE.md to a safe opt-in default (your own C:/E:/ grant
  was your explicit choice; it doesn't carry over silently).

  Your Claude Code login is never at risk here regardless -- it lives
  in your Windows user profile (C:\Users\<you>\.claude\), never inside
  this project folder, so it can't be copied even by accident.

.PARAMETER Destination
  Where to write the clean export. Defaults to C:\JarvisExport.
#>
param(
    [string]$Destination = "C:\JarvisExport"
)

$Source = "C:\AI-Agent"

if (Test-Path $Destination) {
    Write-Host "Destination $Destination already exists." -ForegroundColor Yellow
    $answer = Read-Host "Delete and rebuild it? (y/N)"
    if ($answer -ne "y") { Write-Host "Aborted."; exit 1 }
    Remove-Item -Recurse -Force $Destination
}
New-Item -ItemType Directory -Path $Destination | Out-Null

Write-Host "Copying $Source -> $Destination (this takes a few minutes)..." -ForegroundColor Cyan

$excludeDirs = @(
    ".git",
    "venv", "backtalk\.venv", "backtalk\logs",
    "__pycache__", "build", "dist",
    "JarvisMemory", "voice_cache", "temp_screenshots",
    "conversation_v4_backups", "intelligence_v3_backups",
    "link_search_v4_backups", "search_intelligence_backups",
    "tool_intelligence_backups", "ui_backups",
    "ClaudeCodeBrainV1", "ConversationIntelligenceV4", "IntelligenceCoreV3",
    "LinkSearchV4", "MaintainerV2", "SearchIntelligenceV3",
    "SearchResponseHygieneV5", "ToolIntelligenceV1", "NEW JARVIS",
    ".maintenance_v2\installations",
    "ai-visualizer\.edge-app-profile",
    "_build_tools",
    # Jarvis now builds real deliverables (websites, scripts) directly
    # when asked, straight into the project root by default -- those
    # are the user's own generated content, not part of Jarvis itself,
    # and must never end up bundled into the public friend-edition
    # installer. Add any other project-output folder names here as
    # they come up.
    "website"
) | ForEach-Object { Join-Path $Source $_ }

$excludeFiles = @(
    "*_backup_*.py",
    ".remote_chat_token",
    "*.log",
    "jarvis_live_debug.log",
    "*_error.txt",
    "*startup_error*",
    "*.bak_*",
    "piper_windows_amd64.zip",
    "vosk-model-*.zip",
    "_hud_*.png",
    "JarvisSetup.exe"
)

robocopy $Source $Destination /E /XD $excludeDirs /XF $excludeFiles /NFL /NDL /NJH /NP | Out-Null

Write-Host "Copy done. Sanitizing the export (name, file-access default)..." -ForegroundColor Cyan
& "$Source\venv\Scripts\python.exe" "$Source\_build_tools\sanitize_friend_edition.py" $Destination

Write-Host ""
Write-Host "Done. Clean Jarvis export at: $Destination" -ForegroundColor Green
Write-Host "Next: zip that folder and send it, plus FRIEND_SETUP.md for what he needs to do on his end." -ForegroundColor Green
