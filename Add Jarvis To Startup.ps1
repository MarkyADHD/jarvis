$WshShell = New-Object -ComObject WScript.Shell

$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Jarvis.lnk"

$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "C:\AI-Agent\venv\Scripts\pythonw.exe"
$shortcut.Arguments = '"C:\AI-Agent\jarvis_app_v2.py"'
$shortcut.WorkingDirectory = "C:\AI-Agent"
$shortcut.Description = "Start Jarvis with Windows"
$shortcut.WindowStyle = 7
$shortcut.IconLocation = "C:\AI-Agent\jarvis_icon.ico"
$shortcut.Save()

Write-Host ""
Write-Host "Jarvis added to Windows Startup."
Write-Host "Shortcut:"
Write-Host $shortcutPath
