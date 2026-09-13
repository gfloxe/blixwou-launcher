# Publier les mises à jour BLIXWOU

La version de référence est `appVersion` dans launcher-config.json. Le script aligne pyproject.toml et le compilateur transmet la version à Inno Setup. Ne changez pas l’AppId.

Depuis le dossier du projet, avec GitHub CLI déjà connecté et l’identité Git configurée :

```powershell
.\tools\release.ps1 -Version 0.1.1 -PrivateKeyFile 'C:\chemin-prive\blixwou-update.key'
```

Le script construit avec les contrôles Release, signe les octets définitifs avec Ed25519, vérifie la signature, génère l’appcast, publie l’installateur dans gfloxe/blixwou-launcher, puis seulement publie appcast.xml sur main. Une Release existante n’est jamais écrasée. Un dossier output/blixwou-launcher déjà présent doit être archivé avant une nouvelle publication. En cas d’échec, les versions sources sont restaurées ; inspectez les opérations distantes éventuellement déjà réussies avant toute reprise.

La clé privée reste hors du projet. Seul winsparkle-tool reçoit son chemin. Ne la copiez jamais dans le dépôt. Les outils nécessaires sont déjà présents, notamment vendor/inno/ISCC.exe et GitHub CLI dans Program Files.

## Essai sans publication

```powershell
.\tools\release.ps1 -Version 0.1.1 -PrivateKeyFile 'C:\temp\cle-jetable.key' -DryRun -PublicKeyOverride '<clé publique jetable>'
```

DryRun construit et signe réellement avec la clé jetable, écrit output/appcast.xml, mais ne clone ni ne publie rien. Il restaure ensuite les versions sources. PublicKeyOverride est interdit en publication réelle et ne change pas la clé embarquée. L’installateur et l’appcast issus de cet essai ne doivent pas être distribués : la signature jetable ne correspond pas à la clé publique de production. Reconstruire normalement après l’essai.

WinSparkle vérifie sans fenêtre de progression à chaque démarrage. Les callbacks empêchent l’arrêt pendant une synchronisation ou une partie. En installation interactive, la case Ouvrir BLIXWOU reste proposée ; en installation silencieuse, une entrée distincte relance le programme. Les données dans %LOCALAPPDATA%\BLIXWOU sont conservées.

Les joueurs en 0.1.0 doivent installer manuellement la première version configurée, une seule fois. L’installateur n’est pas signé Authenticode : SmartScreen peut afficher un avertissement. Ed25519 est une vérification distincte, utilisée par WinSparkle.

À tester avant d’affirmer que le parcours fonctionne : installation silencieuse réelle et vraie mise à jour 0.1.1 → 0.1.2, avec conservation des données et relance unique.
