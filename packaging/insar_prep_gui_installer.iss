; Inno Setup script for the insar-prep desktop GUI (Task 053 release packaging).
;
; Wraps the one-file GUI executable (dist\insar-prep-gui.exe, built by
; scripts\build_windows_gui_exe.ps1) into a standard Windows installer with a
; Start Menu entry, an optional desktop shortcut, and an uninstaller. It installs
; per-user by default (no admin required) into %LOCALAPPDATA%\Programs.
;
; Build it with Inno Setup 6 (https://jrsoftware.org/isdl.php):
;     iscc packaging\insar_prep_gui_installer.iss
; or run scripts\build_windows_installer.ps1, which locates iscc and passes the
; version. The compiled installer is written to dist\ and is git-ignored.
;
; Note: the GUI exe must already be built (run the GUI build script first). The
; bundled EGM96 geoid grid and rasterio/GDAL travel inside the one-file exe, so
; no extra data files are installed here.

#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif
#define AppName "InSAR Prep Assistant"
#define AppPublisher "hhanmj"
#define AppURL "https://github.com/hhanmj/insar_assistant"
#define GuiExeName "insar-prep-gui.exe"

[Setup]
AppId={{8E2C4F2A-3B7D-4C1E-9A6F-2D5B1E7C9A40}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={localappdata}\Programs\InSARPrepAssistant
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=insar-prep-gui-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#GuiExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#GuiExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#GuiExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#GuiExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
