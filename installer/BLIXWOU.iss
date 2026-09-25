#define AppName "BLIXWOU"
#ifndef AppVersion
  #error AppVersion must be supplied by tools/build_windows.ps1
#endif

[Setup]
AppId={{CD30760D-C9B2-44EA-A7E2-4468C8A2F98B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=gfloxe
DefaultDirName={localappdata}\Programs\BLIXWOU
DefaultGroupName=BLIXWOU
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist\installer
OutputBaseFilename=BLIXWOU-Setup-{#AppVersion}-x64
SetupIconFile=..\assets\blixwou.ico
UninstallDisplayIcon={app}\BLIXWOU.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dark
WizardBackColor=#150F23
WizardBackImageFile=..\assets\landscape.png
WizardBackImageOpacity=65
WizardImageFile=
WizardSmallImageFile=
WizardSizePercent=120
DisableWelcomePage=no
UninstallDisplayName=BLIXWOU
AppPublisherURL=https://github.com/gfloxe/BLIXWOU
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; Flags: unchecked

[Files]
Source: "..\dist\BLIXWOU\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BLIXWOU"; Filename: "{app}\BLIXWOU.exe"
Name: "{group}\Désinstaller BLIXWOU"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BLIXWOU"; Filename: "{app}\BLIXWOU.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BLIXWOU.exe"; Description: "Ouvrir BLIXWOU"; Flags: nowait postinstall skipifsilent
Filename: "{app}\BLIXWOU.exe"; Flags: nowait; Check: WizardSilent

; No UninstallDelete entry for %LOCALAPPDATA%\BLIXWOU:
; game data, screenshots, personal settings and saves are preserved.

[Messages]
WelcomeLabel1=Bienvenue dans BLIXWOU
WelcomeLabel2=Votre aventure commence ici.%n%nInstallez le launcher BLIXWOU pour retrouver votre serveur et synchroniser automatiquement vos mods et shaders.%n%nMinecraft 1.21.1 · NeoForge 21.1.250%n%nAu premier lancement, les fichiers du jeu seront téléchargés. Une connexion Internet est nécessaire.
FinishedHeadingLabel=BLIXWOU est prêt
FinishedLabel=Le launcher est installé. Vous pouvez maintenant ouvrir BLIXWOU.%n%nPour le retirer, utilisez « Désinstaller BLIXWOU » dans le menu Démarrer ou les applications installées de Windows. Vos sauvegardes et données de jeu seront conservées.
