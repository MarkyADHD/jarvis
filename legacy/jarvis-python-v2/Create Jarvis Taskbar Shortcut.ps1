$WshShell = New-Object -ComObject WScript.Shell

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Jarvis.lnk"

$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "C:\AI-Agent\venv\Scripts\pythonw.exe"
$shortcut.Arguments = '"C:\AI-Agent\jarvis_app_v2.py"'
$shortcut.WorkingDirectory = "C:\AI-Agent"
$shortcut.Description = "Launch Jarvis"
$shortcut.WindowStyle = 7
$shortcut.IconLocation = "C:\AI-Agent\jarvis_icon.ico"
$shortcut.Save()

Write-Host ""
Write-Host "Created:"
Write-Host $shortcutPath
Write-Host ""
Write-Host "Right-click the Jarvis shortcut and choose 'Pin to taskbar'."
