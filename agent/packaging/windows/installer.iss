; =============================================================================
; Apollo Agent V1.7.R - Inno Setup Installer Script
; =============================================================================
;
; Prerequisites:
;   - Build apollo-agent.exe first (build_windows.bat or build_windows.py)
;   - Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
;
; Build:
;   iscc installer.iss
;
; Output:
;   output/APOLLO_DataAuditor_Setup_1.7.R_x64.exe
;
; Flow client:
;   Install -> lance UI (--serve) -> navigateur s'ouvre -> login.html
;   -> client saisit X-API-KEY -> dashboard fonctionnel
;
; Copyright: (c) 2025-2026 aiia-tech.com
; =============================================================================

#define MyAppName "Apollo Data Auditor Agent"
#define MyAppVersion "1.7.R"
#define MyAppPublisher "Apollo Data Auditor"
#define MyAppURL "https://apollo-cloud-api-production.up.railway.app"
#define MyAppExeName "apollo-agent.exe"
#define MyAppServiceName "ApolloAgent"

[Setup]
AppId={{A7B3C4D5-E6F7-8901-2345-6789ABCDEF01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\Apollo Agent
DefaultGroupName=Apollo Agent
AllowNoIcons=yes
LicenseFile=..\..\..\LICENSE
OutputDir=output
OutputBaseFilename=APOLLO_DataAuditor_Setup_{#MyAppVersion}_x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
; Add {app} to system PATH so apollo-agent is accessible from any terminal
ChangesEnvironment=yes
;SetupIconFile=apollo_icon.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
french.InstallService=Installer comme service Windows (d%e9marrage automatique)
french.AddToPath=Ajouter Apollo Agent au PATH syst%e8me
french.LaunchAfterInstall=Lancer Apollo Agent (ouvre le navigateur)
english.InstallService=Install as Windows service (automatic startup)
english.AddToPath=Add Apollo Agent to system PATH
english.LaunchAfterInstall=Launch Apollo Agent (opens browser)

[Tasks]
Name: "addtopath"; Description: "{cm:AddToPath}"; GroupDescription: "Options :"; Flags: checkedonce
Name: "installservice"; Description: "{cm:InstallService}"; GroupDescription: "Options :"

[Files]
; Main binary (built by Nuitka — includes UI static files)
Source: "dist\apollo-agent.exe"; DestDir: "{app}"; Flags: ignoreversion
; Rust native module (if separate from Nuitka bundle)
Source: "dist\apollo_io_native.pyd"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
; Configuration
Source: "..\..\..\agent\config\exclusions.yaml"; DestDir: "{app}\config"; Flags: ignoreversion
; Version file
Source: "..\..\..\agent\VERSION"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{commonappdata}\Apollo"; Permissions: users-modify
Name: "{commonappdata}\Apollo\logs"
Name: "{commonappdata}\Apollo\output"

[Icons]
Name: "{group}\Apollo Agent"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--serve"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Apollo Agent"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--serve"

[Run]
; Register service if selected
Filename: "{app}\{#MyAppExeName}"; Parameters: "service install"; Tasks: installservice; StatusMsg: "Installing Apollo Agent service..."; Flags: runhidden
; Start service
Filename: "net"; Parameters: "start {#MyAppServiceName}"; Tasks: installservice; StatusMsg: "Starting Apollo Agent service..."; Flags: runhidden skipifdoesntexist
; Launch UI after install (opens browser with login page)
Filename: "{app}\{#MyAppExeName}"; Parameters: "--serve"; Description: "{cm:LaunchAfterInstall}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
; Stop and remove service
Filename: "net"; Parameters: "stop {#MyAppServiceName}"; Flags: runhidden
Filename: "{app}\{#MyAppExeName}"; Parameters: "service uninstall"; Flags: runhidden skipifdoesntexist

[Registry]
; Add {app} to system PATH (if task selected)
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  { Look for the path with leading and trailing semicolons }
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;
