; Inno Setup installer for the modern pywebview desktop app.
;
; Build with scripts\build_windows_desktop_installer.ps1 after
; dist\insar-prep-desktop.exe has been generated.

#ifndef AppVersion
  #define AppVersion "2.1"
#endif
#define AppName "InSAR Studio"
#define AppPublisher "hhanmj"
#define AppURL "https://github.com/hhanmj/insar_studio"
#define DesktopExeName "insar-prep-desktop.exe"

[Setup]
AppId={{35F6247A-8B30-4F4A-A7F7-A6AE831B77F1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={localappdata}\Programs\InSAR Studio
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=insar-studio-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#DesktopExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#DesktopExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#DesktopExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#DesktopExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#DesktopExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
