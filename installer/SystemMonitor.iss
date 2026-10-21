; Inno Setup script for System Monitor. Build with build_exe.ps1, which runs
; PyInstaller first, gathers the LibreHardwareMonitor library into SensorLib,
; and passes the details from app_info.py plus DistDir and SensorLibDir.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Amanullah"
#endif
#ifndef AppUrl
  #define AppUrl "https://github.com/amanullah-rao"
#endif
#ifndef AppRepoUrl
  #define AppRepoUrl "https://github.com/amanullah-rao/system-monitor"
#endif
#ifndef AppCopyright
  #define AppCopyright "© 2026 Amanullah"
#endif
#ifndef AppDescription
  #define AppDescription "Live CPU, memory, disk, network and temperature monitor for Windows"
#endif
#ifndef DistDir
  #define DistDir "..\dist\System Monitor"
#endif
#ifndef SensorLibDir
  #define SensorLibDir "..\build\sensor-lib"
#endif
#define AppName "System Monitor"
#define AppExe "System Monitor.exe"

[Setup]
; Keep AppId the same in every release so updates replace the installed copy.
AppId={{8E6F3B0A-6C1D-4E7B-9C55-2F4A1D9B7E21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppRepoUrl}/issues
AppUpdatesURL={#AppRepoUrl}/releases
AppContact={#AppRepoUrl}/issues
AppCopyright={#AppCopyright}
AppComments={#AppDescription}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright={#AppCopyright}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
; Program Files and the CPU temperature task need administrator rights.
PrivilegesRequired=admin
; The sign-in entry is written for the person installing.
UsedUserAreasWarning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=System Monitor Setup
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "autostart"; Description: "Start System Monitor when I sign in to Windows"; GroupDescription: "Startup:"
Name: "sensors"; Description: "Show CPU temperature (adds a small background sensor reader)"; GroupDescription: "CPU temperature:"
Name: "sensors\pawnio"; Description: "Install the PawnIO hardware driver it needs (downloads with winget)"; GroupDescription: "CPU temperature:"; Check: not PawnIOInstalled

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Excludes: "sensor_setup.ps1,sensor_install.ps1,sensor_helper.ps1,README.md"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\sensor_helper.ps1"; DestDir: "{app}\sensor"; Flags: ignoreversion; Tasks: sensors
Source: "..\sensor_install.ps1"; DestDir: "{app}\sensor"; Flags: ignoreversion; Tasks: sensors
Source: "{#SensorLibDir}\*.dll"; DestDir: "{app}\sensor\lib"; Flags: ignoreversion; Tasks: sensors
Source: "..\sensor_uninstall.ps1"; DestDir: "{app}\sensor"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SystemMonitor"; ValueData: """{app}\{#AppExe}"" --autostart"; Tasks: autostart

[Run]
Filename: "{cmd}"; Parameters: "/c winget install --id namazso.PawnIO --exact --source winget --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "Installing the PawnIO driver..."; Flags: runhidden waituntilterminated; Tasks: sensors\pawnio
Filename: "powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\sensor\sensor_install.ps1"" -HelperDir ""{app}\sensor"" -RemoveLegacyCopy"; StatusMsg: "Setting up CPU temperature..."; Flags: runhidden waituntilterminated; Tasks: sensors
Filename: "{app}\{#AppExe}"; Description: "Open System Monitor"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/f /im ""{#AppExe}"""; Flags: runhidden waituntilterminated; RunOnceId: "StopApp"
Filename: "powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\sensor\sensor_uninstall.ps1"" -AppDir ""{app}"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveSensors"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\sensor"

[Code]
function PawnIOInstalled: Boolean;
begin
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\PawnIO');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { Closing the window only hides the app to the tray, so stop it outright
    before replacing its files. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im "{#AppExe}"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
