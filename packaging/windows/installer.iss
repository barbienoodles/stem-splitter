; Inno Setup: crea BananaSplit-Setup.exe da dist\BananaSplit (PyInstaller).
; Compilare dalla radice del repository: iscc /DAppVersion=0.2.1 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.2.1"
#endif

[Setup]
AppId={{0A0EFE82-0833-4FC7-ABC6-6B6FB6B9F767}
AppName=Banana Split
AppVersion={#AppVersion}
AppPublisher=barbienoodles
DefaultDirName={localappdata}\Programs\Banana Split
DefaultGroupName=Banana Split
; installazione per l'utente corrente: non servono i permessi di amministratore
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=BananaSplit-{#AppVersion}-Windows-Setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\BananaSplit.exe
Compression=lzma2/ultra64
LZMADictionarySize=262144
LZMANumFastBytes=273
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\BananaSplit\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Banana Split"; Filename: "{app}\BananaSplit.exe"
Name: "{autodesktop}\Banana Split"; Filename: "{app}\BananaSplit.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BananaSplit.exe"; Description: "{cm:LaunchProgram,Banana Split}"; Flags: nowait postinstall skipifsilent
