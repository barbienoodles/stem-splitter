; Inno Setup: crea StemSplitter-Setup.exe da dist\StemSplitter (PyInstaller).
; Compilare dalla radice del repository: iscc /DAppVersion=0.1.0 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6E0B9D5C-2A4F-4C7B-9E3D-5A1F3C8B7D21}
AppName=Stem Splitter
AppVersion={#AppVersion}
AppPublisher=barbienoodles
DefaultDirName={localappdata}\Programs\Stem Splitter
DefaultGroupName=Stem Splitter
; installazione per l'utente corrente: non servono i permessi di amministratore
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=StemSplitter-{#AppVersion}-Windows-Setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\StemSplitter.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\StemSplitter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Stem Splitter"; Filename: "{app}\StemSplitter.exe"
Name: "{autodesktop}\Stem Splitter"; Filename: "{app}\StemSplitter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\StemSplitter.exe"; Description: "{cm:LaunchProgram,Stem Splitter}"; Flags: nowait postinstall skipifsilent
