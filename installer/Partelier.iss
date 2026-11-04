#ifndef AppVersion
  #error AppVersion must be supplied by tools/build_installer.py
#endif
#ifndef PayloadDir
  #error PayloadDir must be supplied by tools/build_installer.py
#endif

[Setup]
AppId={code:InstallerIdentity}
AppName=Partelier
AppVersion={#AppVersion}
AppPublisher=EsKay Labs
AppPublisherURL=https://github.com/EsKay-Labs/Partelier
AppSupportURL=https://github.com/EsKay-Labs/Partelier/issues
AppUpdatesURL=https://github.com/EsKay-Labs/Partelier/releases/latest
DefaultDirName={userappdata}\Autodesk\Autodesk Fusion 360\API\AddIns\Partelier
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=no
UsePreviousLanguage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
UninstallDisplayName=Partelier for Autodesk Fusion
UninstallDisplayIcon={app}\Partelier.ico
SetupIconFile=..\Partelier\partelier\resources\launcher\Partelier.ico
OutputBaseFilename=Partelier-{#AppVersion}-Windows-Setup
VersionInfoVersion={#AppVersion}
VersionInfoCompany=EsKay Labs
VersionInfoDescription=Partelier installer for Autodesk Fusion
InfoAfterFile=finished.txt

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Code]
function HasFlag(Value: String): Boolean;
var I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if Uppercase(ParamStr(I)) = Value then Result := True;
end;

function HasTestFlag: Boolean;
begin
  Result := HasFlag('/TESTINSTALL');
end;

function InstallerIdentity(Param: String): String;
begin
  if HasTestFlag then Result := 'Partelier-Installer-Smoke-Test-24bc721a'
  else Result := 'Partelier-EsKayLabs-7947c039-0f77-43fb-a7c3-2ce8b118dc28';
end;

function IsTestDirectory: Boolean;
var Prefix, Target: String;
begin
  Prefix := Lowercase(AddBackslash(ExpandFileName(GetEnv('TEMP') + '\PartelierInstallerTest')));
  Target := Lowercase(AddBackslash(ExpandFileName(ExpandConstant('{app}'))));
  Result := HasTestFlag and (Pos(Prefix, Target) = 1) and (Length(Target) > Length(Prefix));
end;

function FusionIsRunning: Boolean;
var Locator, Service, Processes: Variant;
begin
  { Fail closed if process detection is unavailable. Never terminate Fusion. }
  Result := True;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Processes := Service.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''Fusion360.exe''');
    Result := Processes.Count > 0;
  except
    Log('Could not check Fusion processes. Close Fusion before retrying Setup.');
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Target, Expected: String;
begin
  Result := '';
  Target := Lowercase(ExpandFileName(ExpandConstant('{app}')));
  Expected := Lowercase(ExpandFileName(ExpandConstant('{userappdata}\Autodesk\Autodesk Fusion 360\API\AddIns\Partelier')));
  if HasTestFlag and not IsTestDirectory then begin
    Result := 'Test installs must use a unique subfolder of TEMP\PartelierInstallerTest.';
    Exit;
  end;
  if not IsTestDirectory and (Target <> Expected) then begin
    Result := 'Partelier must be installed in the current user Fusion AddIns folder.';
    Exit;
  end;
  if (not IsTestDirectory or HasFlag('/CHECKFUSION')) and FusionIsRunning then begin
    Result := 'Save your work and close Autodesk Fusion, then retry. Setup will not close it for you.';
    Exit;
  end;
  if DirExists(ExpandConstant('{app}')) and
     not FileExists(ExpandConstant('{app}\.partelier-installer')) then begin
    Result := 'This Partelier folder was not installed by this installer. Move or back up that manual installation before retrying. Your files have not been changed.';
    Exit;
  end;
end;

function InitializeUninstall: Boolean;
begin
  Result := IsTestDirectory or not FusionIsRunning;
  if not Result then
    SuppressibleMsgBox('Save your work and close Autodesk Fusion before uninstalling Partelier.', mbInformation, MB_OK, IDOK);
end;
