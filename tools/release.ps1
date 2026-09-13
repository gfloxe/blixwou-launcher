param([Parameter(Mandatory)][string]$Version, [string]$PrivateKeyFile='', [switch]$DryRun, [switch]$ResumeAppcast, [string]$PublicKeyOverride='')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$root=(Get-Location).Path
$gh='C:\Program Files\GitHub CLI\gh.exe'
$python=Join-Path $root '.venv\Scripts\python.exe'
$tool=Join-Path $root 'vendor\winsparkle-tool.exe'
$repo='gfloxe/blixwou-launcher'
$tag="v$Version"
$configPath=Join-Path $root 'launcher-config.json'
$projectPath=Join-Path $root 'pyproject.toml'
$appcast=Join-Path $root "output\appcast-$Version.xml"
$installer=Join-Path $root "dist\installer\BLIXWOU-Setup-$Version-x64.exe"
function Assert-Exit([string]$Message) { if ($LASTEXITCODE -ne 0) { throw $Message } }
function Assert-Clean {
    $status=& git status --porcelain
    Assert-Exit 'Impossible de vérifier le dépôt Git.'
    if ($status) {
        if ($ResumeAppcast -and (Test-Path -LiteralPath $appcast) -and
            -not (@($status) | Where-Object { $_.Substring(3) -ne 'appcast.xml' })) { return }
        throw 'Commitez les modifications avant de préparer une version.'
    }
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'La version doit être X.Y.Z.' }
if ($PublicKeyOverride -and -not $DryRun) { throw 'Clé de test réservée à -DryRun.' }
if ($ResumeAppcast -and $DryRun) { throw 'Choisissez -ResumeAppcast ou -DryRun.' }
$branch=& git branch --show-current
if ($branch -ne 'main') { throw 'La publication exige main.' }
Assert-Clean
$origin=& git remote get-url origin
Assert-Exit 'Remote origin absent.'
if ($origin -notin @("https://github.com/$repo.git","https://github.com/$repo")) { throw 'Remote origin incorrect.' }
& $gh auth status *> $null
Assert-Exit 'Connectez vous-même GitHub CLI.'
& git pull --ff-only
Assert-Exit 'git pull --ff-only a échoué.'
Assert-Clean
$oldConfig=[IO.File]::ReadAllText($configPath)
$oldProject=[IO.File]::ReadAllText($projectPath)
$config=$oldConfig | ConvertFrom-Json
$publicKey=$config.launcherUpdate.ed25519PublicKey
if ($PublicKeyOverride) { $publicKey=$PublicKeyOverride }
foreach ($field in @('user.name','user.email')) {
    $value=& git config $field
    Assert-Exit "Configurez git $field."
    if (-not $value) { throw "Configurez git $field." }
}
$releases=@(& $gh api --paginate "repos/$repo/releases" --jq '.[].tag_name')
Assert-Exit 'Impossible de vérifier les Releases.'
function Publish-Appcast {
    & $python tools\verify_release_asset.py --version $Version --installer $installer --appcast $appcast
    Assert-Exit 'Le fichier publié ou sa signature ne correspond pas.'
    Copy-Item -LiteralPath $appcast -Destination (Join-Path $root 'appcast.xml')
    & git add appcast.xml
    Assert-Exit 'Préparation du commit appcast impossible.'
    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        & git commit -m "Publier BLIXWOU $Version"
        Assert-Exit 'Commit appcast échoué.'
    }
    & git push origin main
    Assert-Exit 'Push appcast échoué : relancez avec -ResumeAppcast.'
}
if ($ResumeAppcast) {
    if ($releases -notcontains $tag) { throw 'Release absente ; reprise impossible.' }
    Publish-Appcast
    Write-Output "Appcast $Version publié ; Release conservée."
    return
}
if ([version]$Version -le [version]$config.appVersion) { throw 'La version doit être supérieure à la version actuelle.' }
if ($releases -contains $tag) { throw "La Release $tag existe déjà ; aucun écrasement." }
& git show-ref --verify --quiet "refs/tags/$tag"
if ($LASTEXITCODE -eq 0) { throw "Le tag $tag existe déjà." }
if (-not (Test-Path -LiteralPath $PrivateKeyFile -PathType Leaf)) { throw 'Fichier de clé privée introuvable.' }
$PrivateKeyFile=(Resolve-Path -LiteralPath $PrivateKeyFile).Path
& $python -m pytest -q
Assert-Exit 'Les tests préalables ont échoué.'
Assert-Clean
$base=& git rev-parse HEAD
$committed=$false; $tagCreated=$false; $pushed=$false; $released=$false; $success=$false
try {
    $config.appVersion=$Version
    [IO.File]::WriteAllText($configPath,($config | ConvertTo-Json -Depth 10)+"`n")
    [IO.File]::WriteAllText($projectPath,([regex]::Replace($oldProject,'(?m)^version = "[^"]+"',"version = `"$Version`"")))
    & "$PSScriptRoot\build_windows.ps1" -Installer -Release
    $signed=& $tool sign --private-key-file $PrivateKeyFile $installer
    Assert-Exit 'Signature échouée.'
    $signature=[regex]::Match(($signed -join "`n"),'[A-Za-z0-9+/]{86}==').Value
    if (-not $signature) { throw 'Signature Ed25519 introuvable.' }
    & $tool verify --public-key $publicKey --signature $signature $installer
    Assert-Exit 'Signature refusée : publication arrêtée.'
    $url="https://github.com/$repo/releases/download/$tag/BLIXWOU-Setup-$Version-x64.exe"
    & $python tools\make_appcast.py --installer $installer --version $Version --url $url --signature $signature --output $appcast
    Assert-Exit 'Génération appcast échouée.'
    Copy-Item -LiteralPath $appcast -Destination (Join-Path $root 'output\appcast.xml')
    if ($DryRun) {
        Write-Output 'DRYRUN OK : installateur signé et appcast généré ; aucun commit, tag, push ou Release.'
        Write-Output "Prévu : commit Version $Version ; tag $tag ; push atomique main + tag ; gh release create --verify-tag ; commit appcast ; push main."
        return
    }
    & git add launcher-config.json pyproject.toml
    Assert-Exit 'Préparation version échouée.'
    & git commit -m "Version $Version"
    Assert-Exit 'Commit version échoué.'
    $committed=$true
    $publicationCommit=& git rev-parse HEAD
    & git tag $tag
    Assert-Exit 'Création tag échouée.'
    $tagCreated=$true
    & git push --atomic origin main "refs/tags/$tag"
    Assert-Exit 'Push de version échoué.'
    $pushed=$true
    & $gh release create $tag $installer --repo $repo --verify-tag --title "BLIXWOU $Version" --notes "Mise à jour du launcher BLIXWOU $Version."
    Assert-Exit 'Création de Release échouée.'
    $released=$true
    Publish-Appcast
    $success=$true
    Write-Output "BLIXWOU $Version publié et appcast mis à jour."
} catch {
    $problem=$_
    if ($tagCreated -and -not $pushed) {
        $remoteTag=& git ls-remote origin "refs/tags/$tag"
        if ($LASTEXITCODE -ne 0) {
            $released=$true
            Write-Warning 'Résultat du push incertain : aucun retour arrière automatique. Vérifiez GitHub.'
        } elseif ($remoteTag -and $remoteTag.StartsWith($publicationCommit)) { $pushed=$true }
    }
    if ($pushed -and -not $released) {
        $check=@(& $gh api --paginate "repos/$repo/releases" --jq '.[].tag_name')
        if ($LASTEXITCODE -ne 0) {
            $released=$true
            Write-Warning 'État distant incertain : version et tag conservés. Vérifiez GitHub.'
        } elseif ($check -contains $tag) { $released=$true }
    }
    if ($released) { Write-Warning "Release potentiellement créée, aucun écrasement. Reprise : .\tools\release.ps1 -Version $Version -ResumeAppcast" }
    throw $problem
} finally {
    if ($DryRun -or (-not $success -and -not $released)) {
        [IO.File]::WriteAllText($configPath,$oldConfig)
        [IO.File]::WriteAllText($projectPath,$oldProject)
        if ($committed -and -not $pushed) {
            & git reset --soft $base
            & git restore --staged -- launcher-config.json pyproject.toml
            if ($tagCreated) { & git tag -d $tag }
        } elseif ($pushed) {
            # Required order pushes code before creating a release. Compensate without rewriting history.
            & git add launcher-config.json pyproject.toml
            & git commit -m "Annuler la préparation de $Version après échec de publication"
            if ($LASTEXITCODE -eq 0) {
                & git push --atomic origin main ":refs/tags/$tag"
                if ($LASTEXITCODE -eq 0) { & git tag -d $tag }
                else { Write-Warning 'Retour de version distant échoué ; appcast inchangé. Vérifiez main.' }
            }
        }
    }
}
