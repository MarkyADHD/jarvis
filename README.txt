JARVIS LAUNCHER
===============

FILES

Launch Jarvis.bat
    Normal launcher.
    Uses pythonw.exe so no console window stays open.

Launch Jarvis Debug.bat
    Development launcher.
    Uses python.exe and keeps the console visible so you can see errors.

Create Jarvis Taskbar Shortcut.ps1
    Creates Jarvis.lnk on your Desktop.
    Right-click Jarvis.lnk -> Pin to taskbar.

Add Jarvis To Startup.ps1
    Adds a Jarvis shortcut to your Windows Startup folder.


INSTALL

Copy these files into:

C:\AI-Agent


NORMAL LAUNCH

Double-click:

Launch Jarvis.bat


TASKBAR

Open PowerShell:

cd C:\AI-Agent

powershell -ExecutionPolicy Bypass -File ".\Create Jarvis Taskbar Shortcut.ps1"

A Jarvis shortcut will appear on your Desktop.

Right-click it:
Show more options if necessary
-> Pin to taskbar


START WITH WINDOWS

Run:

cd C:\AI-Agent

powershell -ExecutionPolicy Bypass -File ".\Add Jarvis To Startup.ps1"

Jarvis will then launch when you sign into Windows.


REMOVE FROM STARTUP

Press:

Win + R

Enter:

shell:startup

Delete:

Jarvis.lnk


DEVELOPMENT

If Jarvis suddenly refuses to start, use:

Launch Jarvis Debug.bat

That keeps the command window open so you can see the Python error instead of
pythonw.exe failing silently.
