; SAM Autonomous AI Assistant — Inno Setup Installer Script
; Version: 7.0.0
; Target: Windows 11 x64
;
; Build requirements:
;   1. Install Inno Setup 6.x from https://jrsoftware.org/isinfo.php
;   2. Build the PyInstaller bundle first: pyinstaller SAM.spec --noconfirm
;   3. Compile this script: iscc packaging\sam_installer.iss
;      Output: packaging\output\SAM_Setup_7.0.0.exe
;
; Design goals:
;   - Application binaries → Program Files\SAM
;   - User data            → %APPDATA%\SAM    (preserved on upgrade/uninstall)
;   - No admin write to user data directories
;   - Upgrade-safe: uninstalls previous version before installing new one

#define MyAppName      "SAM"
#define MyAppVersion   "7.0.0"
#define MyAppPublisher "Sumit Kumar"
#define MyAppURL       "https://github.com/Sumit2003-dev/Personal-AI-Assistant"
#define MyAppExeName   "SAM.exe"
#define MySourceDir    "..\dist\SAM"
#define MyOutputDir    "output"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
InfoBeforeFile=..\packaging\scripts\pre_install_info.txt
InfoAfterFile=..\packaging\scripts\post_install_info.txt
OutputDir={#MyOutputDir}
OutputBaseFilename=SAM_Setup_{#MyAppVersion}
SetupIconFile=..\packaging\assets\sam_icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Minimum Windows 10 (build 10240)
MinVersion=10.0.10240
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=SAM Autonomous AI Desktop Assistant
VersionInfoProductName={#MyAppName}
ChangesAssociations=no
; Prevent running during install/uninstall
CloseApplications=yes
CloseApplicationsFilter=*SAM.exe*

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "Create a &desktop shortcut";      GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startupentry";  Description: "Start SAM &automatically at login"; GroupDescription: "Startup:";         Flags: unchecked

[Files]
; Application binaries — the full PyInstaller dist\SAM folder
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Packaging assets
Source: "..\packaging\assets\sam_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}";                     Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\sam_icon.ico"
Name: "{group}\Uninstall {#MyAppName}";           Filename: "{uninstallexe}"

; Desktop (optional)
Name: "{autodesktop}\{#MyAppName}";               Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\sam_icon.ico"; Tasks: desktopicon

[Run]
; Launch SAM after installation (optional)
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Registry]
; Optional Windows startup (matches user task selection)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SAMDesktopApp"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupentry

[UninstallRun]
; Kill running SAM instances before uninstall
Filename: "taskkill.exe"; Parameters: "/F /IM SAM.exe"; Flags: runhidden; RunOnceId: "KillSAM"

[UninstallDelete]
; Remove application binaries — but NOT %APPDATA%\SAM (user data is preserved)
Type: filesandordirs; Name: "{app}"

[Code]
// -------------------------------------------------------------------------
// Upgrade support: silently uninstall the previous version before installing
// -------------------------------------------------------------------------
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion(): Integer;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  Result := 0;
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    if Exec(sUnInstallString, '/SILENT /NORESTART /SUPPRESSMSGBOXES', '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := iResultCode
    else
      Result := 1;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) then begin
    if (IsUpgrade()) then begin
      UnInstallOldVersion();
    end;
  end;
end;
