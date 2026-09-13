param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$PrivateKeyFile,
    [switch]$DryRun,
    [string]$PublicKeyOverride = ''
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$root = (Get-Location).Path
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
$python = Join-Path $root '.venv\Scripts\python.exe'
$tool = Join-Path $root 'vendor\winsparkle-tool.exe'
$configPath = Join-Path $root 'launcher-config.json'
$projectPath = Join-Path $root 'pyproject.toml'
$oldConfig = [IO.File]::ReadAllText($configPath)
$oldProject = [IO.File]::ReadAllText($projectPath)
$config = $oldConfig | ConvertFrom-Json
if ($Version -notmatch '^\d+\.\d+\.\d+$' -or [version]$Version -le [version]$config.appVersion) { throw 'La version doit être X.Y.Z et supérieure à la version actuelle.' }
if ($PublicKeyOverride -and -not $DryRun) { throw 'La clé publique de test est réservée à -DryRun.' }
if (-not (Test-Path -LiteralPath $gh)) { throw 'GitHub CLI est introuvable.' }
& $gh auth status *> $null
if ($LASTEXITCODE -ne 0) { throw 'Connectez vous-même GitHub CLI avant de publier.' }
foreach ($field in @('user.name', 'user.email')) {
    $value = & git config $field
    if ($LASTEXITCODE -ne 0 -or -not $value) { throw "Configurez git $field avant de continuer." }
}
if (-not (Test-Path -LiteralPath $PrivateKeyFile -PathType Leaf)) { throw 'Le fichier de clé privée est introuvable.' }
$PrivateKeyFile = (Resolve-Path -LiteralPath $PrivateKeyFile).Path
$publicKey = $config.launcherUpdate.ed25519PublicKey
if ($PublicKeyOverride) { $publicKey = $PublicKeyOverride }
$repo = 'gfloxe/blixwou-launcher'
$tag = "v$Version"
$completed = $false
try {
    $config.appVersion = $Version
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 10) + "`n")
    [IO.File]::WriteAllText($projectPath, ([regex]::Replace($oldProject, '(?m)^version = "[^"]+"', "version = `"$Version`"")))
    & "$PSScriptRoot\build_windows.ps1" -Installer -Release
    $installer = Join-Path $root "dist\installer\BLIXWOU-Setup-$Version-x64.exe"
    if (-not (Test-Path -LiteralPath $installer)) { throw 'Installateur attendu introuvable.' }
    $signed = & $tool sign --private-key-file $PrivateKeyFile $installer
    if ($LASTEXITCODE -ne 0) { throw 'La signature de lʼinstallateur a échoué.' }
    $signature = [regex]::Match(($signed -join "`n"), '[A-Za-z0-9+/]{86}==').Value
    if (-not $signature) { throw 'Signature Ed25519 introuvable dans la réponse de WinSparkle.' }
    & $tool verify --public-key $publicKey --signature $signature $installer
    if ($LASTEXITCODE -ne 0) { throw 'Signature refusée : publication arrêtée.' }
    $url = "https://github.com/$repo/releases/download/$tag/BLIXWOU-Setup-$Version-x64.exe"
    $appcast = Join-Path $root 'output\appcast.xml'
    & $python tools\make_appcast.py --installer $installer --version $Version --url $url --signature $signature --output $appcast
    if ($LASTEXITCODE -ne 0) { throw 'La génération de lʼappcast a échoué.' }
    if ($DryRun) {
        Write-Output "ESSAI : appcast généré, aucune publication. Commandes prévues :"
        Write-Output "git clone https://github.com/$repo.git output/blixwou-launcher"
        Write-Output 'Si dépôt vide : créer README.md, git checkout -b main, git add README.md, git commit, git push -u origin main'
        Write-Output "gh release list --repo $repo (arrêt si $tag existe)"
        Write-Output "gh release create $tag `"$installer`" --repo $repo --target main --title `"BLIXWOU $Version`""
        Write-Output 'Puis seulement : copier appcast.xml, git add appcast.xml, git commit, git push origin main'
        return
    }
    $releases = & $gh api --paginate "repos/$repo/releases" --jq '.[].tag_name'
    if ($LASTEXITCODE -ne 0) { throw 'Impossible de vérifier les Releases existantes.' }
    if ($releases -contains $tag) { throw "La Release $tag existe déjà ; aucun écrasement autorisé." }
    $checkout = Join-Path $root 'output\blixwou-launcher'
    if (Test-Path -LiteralPath $checkout) { throw 'output\blixwou-launcher existe déjà : archivez cette copie avant de recommencer.' }
    & git clone "https://github.com/$repo.git" $checkout
    if ($LASTEXITCODE -ne 0) { throw 'Échec du clonage.' }
    & git -C $checkout rev-parse --verify HEAD *> $null
    if ($LASTEXITCODE -ne 0) {
        & git -C $checkout checkout -b main
        if ($LASTEXITCODE -ne 0) { throw 'Impossible de créer main.' }
        [IO.File]::WriteAllText((Join-Path $checkout 'README.md'), "# BLIXWOU`n`nInstallateurs Windows et mises à jour du launcher BLIXWOU.`n")
        & git -C $checkout add README.md
        if ($LASTEXITCODE -ne 0) { throw 'Échec de préparation du README.' }
        & git -C $checkout commit -m 'Initialiser la distribution BLIXWOU'
        if ($LASTEXITCODE -ne 0) { throw 'Échec du commit initial.' }
        & git -C $checkout push -u origin main
        if ($LASTEXITCODE -ne 0) { throw 'Échec de publication de main.' }
    }
    & $gh release create $tag $installer --repo $repo --target main --title "BLIXWOU $Version" --notes "Mise à jour du launcher BLIXWOU $Version."
    if ($LASTEXITCODE -ne 0) { throw 'Publication de la Release interrompue ; appcast non publié.' }
    Copy-Item -LiteralPath $appcast -Destination (Join-Path $checkout 'appcast.xml')
    & git -C $checkout add appcast.xml
    if ($LASTEXITCODE -ne 0) { throw 'Échec de préparation de lʼappcast.' }
    & git -C $checkout commit -m "Publier BLIXWOU $Version"
    if ($LASTEXITCODE -ne 0) { throw 'Échec du commit de lʼappcast.' }
    & git -C $checkout push origin main
    if ($LASTEXITCODE -ne 0) { throw 'Release créée mais publication de lʼappcast échouée.' }
    $completed = $true
} finally {
    if ($DryRun -or -not $completed) {
        [IO.File]::WriteAllText($configPath, $oldConfig)
        [IO.File]::WriteAllText($projectPath, $oldProject)
    }
}
