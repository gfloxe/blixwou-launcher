param([switch]$Installer, [switch]$Release, [string]$InnoCompiler = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Créez .venv puis installez les dépendances (README.md).' }
if ($Release) {
    & $python tools\check_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Configuration de publication incomplète.' }
}
& $python tools\bootstrap_vendor.py
if ($LASTEXITCODE -ne 0) { throw 'Échec de la préparation WinSparkle.' }
& $python tools\create_icon.py
& $python tools\collect_licenses.py
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Les tests ont échoué.' }
& $python -m PyInstaller --noconfirm --windowed --onedir --name BLIXWOU --icon assets\blixwou.ico --add-data 'assets;assets' --add-data 'launcher-config.json;.' --add-data 'docs;docs' --add-data 'vendor/WinSparkle.dll;vendor' --add-data 'vendor/COPYING;vendor' --add-data 'vendor/COPYING.expat;vendor' --collect-data minecraft_launcher_lib run.py
if ($LASTEXITCODE -ne 0) { throw 'Échec de PyInstaller.' }
& $python tools\normalize_runtime.py
if ($LASTEXITCODE -ne 0) { throw 'Échec de la préparation du runtime Visual C++.' }
Copy-Item -LiteralPath README.md -Destination dist\BLIXWOU\README.md
if ($Installer) {
    if (-not $InnoCompiler) { $InnoCompiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
    if (-not (Test-Path -LiteralPath $InnoCompiler)) { throw 'Inno Setup 6 requis. Utilisez -InnoCompiler pour préciser ISCC.exe.' }
    & $InnoCompiler installer\BLIXWOU.iss
    if ($LASTEXITCODE -ne 0) { throw "Échec de la compilation de l’installateur." }
}
Write-Output 'Construction terminée : dist\BLIXWOU\BLIXWOU.exe'
