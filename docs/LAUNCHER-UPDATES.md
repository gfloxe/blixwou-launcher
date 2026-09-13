# Mises à jour du launcher

Les mises à jour du **pack** passent par son manifeste. Les mises à jour du **programme BLIXWOU** passent par WinSparkle, son flux appcast et un nouvel installateur. Un modpack ne peut pas remplacer le programme, la DLL WinSparkle ou sa clé publique.

WinSparkle 0.9.4 x64 est téléchargé depuis sa Release officielle par `tools/bootstrap_vendor.py`. Son archive est épinglée à une empreinte SHA-256 récupérée depuis les métadonnées de cette Release. Le fournisseur et ses licences figurent dans `THIRD-PARTY.md`. La DLL est chargée par chemin absolu à l’intérieur de l’application empaquetée.

## Première configuration

1. Exécuter `tools/bootstrap_vendor.py` pour obtenir la DLL et `winsparkle-tool.exe`.
2. Générer la paire de clés **dans un dossier privé hors du dépôt et hors du pack** :

```powershell
.\vendor\winsparkle-tool.exe generate-key --file 'C:\chemin-prive\blixwou-update.key'
```

La clé publique est affichée par l’outil. La copier dans `launcherUpdate.ed25519PublicKey`. Sauvegarder la clé privée hors ligne ; ne jamais la mettre sur GitHub, dans le launcher ou dans une pièce jointe de conversation.

3. Choisir une URL HTTPS stable pour `appcast.xml`, dans un dépôt de publication du launcher. `gfloxe/blixwou-launcher` peut être utilisé s’il est créé ; ce nom n’est **pas un dépôt existant fourni**. Renseigner `launcherUpdate.appcastUrl` uniquement après avoir publié le flux.
4. Embarquer la clé publique et l’URL dans la première version diffusée. Sans ces deux paramètres, l’édition de développement laisse WinSparkle désactivé. Une clé absente, invalide ou refusée par la DLL empêche son activation.

## Signer et publier

1. Augmenter la version du launcher dans les fichiers indiqués dans le README.
2. Construire l’exécutable et l’installateur Inno Setup. Tester sur Windows x64.
3. Si vous possédez un certificat Authenticode, signer l’exécutable et l’installateur avec votre propre certificat et un horodatage, en utilisant SignTool/Windows SDK. La version fournie est non signée Authenticode : aucun certificat d’éditeur n’a été fourni. Cette signature Windows est distincte d’Ed25519 et améliore l’identification de l’éditeur ; ne fabriquez pas de signature de confiance.
4. **Après toute signature Authenticode**, signer les octets définitifs de l’installateur avec WinSparkle :

```powershell
.\vendor\winsparkle-tool.exe sign --help
# Avec la syntaxe confirmée par l’outil :
.\vendor\winsparkle-tool.exe sign --private-key-file 'C:\chemin-prive\blixwou-update.key' .\dist\installer\BLIXWOU-Setup-0.1.0-x64.exe
```

5. Créer l’appcast avec `tools/make_appcast.py`, en passant le fichier final, sa version, sa vraie URL de Release et la signature produite. Exemple de commande à remplir avec des valeurs réelles :

```powershell
.venv\Scripts\python.exe tools\make_appcast.py --installer .\dist\installer\BLIXWOU-Setup-0.1.0-x64.exe --version 0.1.0 --url $urlReelleInstallateur --signature $signatureEd25519 --output .\output\appcast.xml
```

6. Publier l’installateur dans une Release, puis le flux stable. Ne jamais modifier le fichier après signature. WinSparkle vérifie Ed25519 avant d’exécuter l’installateur ; le flux comporte la taille réelle, l’architecture x64 et les arguments Inno Setup avec progression visible.

Les [instructions officielles WinSparkle](https://winsparkle.org/guides/getting-started/) décrivent les clés ; le [guide d’appcast](https://winsparkle.org/guides/publishing-updates/) décrit le flux et les arguments de l’installateur. WinSparkle gère ses propres demandes de vérification de mises à jour et n’encombre pas l’écran principal avec une nouvelle carte.

Un téléchargement de pack et une session Minecraft bloquent l’arrêt demandé par WinSparkle. L’installateur refuse aussi de remplacer le launcher pendant son exécution via un mutex Windows. La désinstallation laisse les données du joueur dans `%LOCALAPPDATA%\BLIXWOU`.

**À valider avant publication publique** : effectuer une mise à jour entre deux builds avec votre clé, puis vérifier qu’un installateur altéré est rejeté. Sans clé du propriétaire, URL de flux et deux versions publiées, aucun essai de mise à jour distante de production n’a été réalisé.
