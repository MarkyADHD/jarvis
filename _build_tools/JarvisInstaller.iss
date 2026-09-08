; JARVIS installer -- Jarvis-themed Inno Setup script.
;
; Build order:
;   1. build_friend_edition.ps1 must have already produced a clean,
;      sanitized export at C:\JarvisExport (memory/secrets/tokens
;      stripped, name/file-access reset -- see that script's own
;      header for what it removes and why).
;   2. generate_installer_art.py must have already written the wizard
;      banner/icon bitmaps into installer_art\.
;   3. Then compile THIS script with ISCC.exe.
;
; Unsigned on purpose (see the conversation this shipped from): a real
; code-signing certificate costs money and needs identity verification
; neither of which this build process can do for you. Windows
; SmartScreen will show an "unknown publisher" warning on first run --
; that's normal for indie-distributed software, not a sign anything is
; actually wrong. FRIEND_SETUP.md explains the one-click way past it.

#define AppName "JARVIS"
#define AppPublisher "MarkyADHD"
#define AppVersion "1.9"
#define ExportDir "C:\JarvisExport"
#define ArtDir "installer_art"

[Setup]
AppId={{6F1B1A9A-6E4A-4B8F-9C6D-3E9C2B7B4C10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName=C:\AI-Agent
DisableDirPage=yes
DefaultGroupName=JARVIS
OutputDir=C:\AI-Agent\_build_tools\dist
OutputBaseFilename=JarvisSetup
SetupIconFile=C:\AI-Agent\jarvis_icon.ico
WizardImageFile={#ArtDir}\wizard_banner.bmp
WizardSmallImageFile={#ArtDir}\wizard_small.bmp
WizardStyle=modern
LicenseFile=LICENSE.txt
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableWelcomePage=no
DisableProgramGroupPage=yes

[Messages]
WelcomeLabel1=Welcome to the %n[name] Setup Wizard
WelcomeLabel2=This installs JARVIS -- a personal AI assistant that runs on your own Claude account, controls your PC, plays your music, and runs your smart lights.%n%nCreated by MarkyADHD.%n%nInstalling to C:\AI-Agent (fixed -- several files reference this path directly).

[Types]
Name: "full"; Description: "Full installation"

[Components]
Name: "main"; Description: "JARVIS core files"; Types: full; Flags: fixed

[Files]
Source: "{#ExportDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: main
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "FRIEND_SETUP.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "setup_environment.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\JARVIS"; Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: """{app}\jarvis_app_v2.py"""; WorkingDir: "{app}"; IconFilename: "{app}\jarvis_icon.ico"
Name: "{group}\Finish Setup (run this first)"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup_environment.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\jarvis_icon.ico"
Name: "{group}\Setup Guide"; Filename: "{app}\FRIEND_SETUP.md"
Name: "{group}\About JARVIS"; Filename: "{app}\README.md"
Name: "{group}\Uninstall JARVIS"; Filename: "{uninstallexe}"
Name: "{commondesktop}\JARVIS"; Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: """{app}\jarvis_app_v2.py"""; WorkingDir: "{app}"; IconFilename: "{app}\jarvis_icon.ico"
Name: "{commonstartup}\JARVIS"; Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: """{app}\jarvis_app_v2.py"""; WorkingDir: "{app}"; IconFilename: "{app}\jarvis_icon.ico"; Comment: "Start Jarvis with Windows"

[Run]
; Deliberately ONE checkbox, not two. An earlier version had a separate
; independent "Launch JARVIS now" entry after this one -- which broke
; for a real user who unchecked "Finish setup" but left "Launch" checked,
; producing "Unable to execute pythonw.exe: the system cannot find the
; file specified" (no venv exists yet at that point). setup_environment.ps1
; now launches Jarvis itself at the very end, where the venv's existence
; is guaranteed rather than assumed from checkbox state.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup_environment.ps1"""; Description: "Finish setup now (Python environment + Claude Code install and login -- takes a few minutes, and will ask you to sign in with your own Claude account -- launches JARVIS automatically when done)"; Flags: postinstall shellexec skipifsilent
Filename: "{app}\FRIEND_SETUP.md"; Description: "Open the setup guide"; Flags: postinstall shellexec skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\backtalk\.venv"
Type: filesandordirs; Name: "{app}\__pycache__"
