# Travail sur BLIXWOU

- Travailler dans ce dépôt pour les modifications du launcher. Préserver les données de `%LOCALAPPDATA%\BLIXWOU`, l’AppId Inno Setup et les versions Minecraft/NeoForge sauf demande explicite.
- Après une modification demandée : lancer pytest, faire un commit clair en français, puis pousser sur main. Ne pas publier de version : les joueurs ne reçoivent rien tant que l’appcast n’est pas mis à jour.
- Seulement quand l’utilisateur dit explicitement « publie la version X.Y.Z », lancer :

```powershell
.\tools\release.ps1 -Version X.Y.Z -PrivateKeyFile "C:\Users\gfloxe\Desktop\Clé privé\blixwou-update.key"
```

- Montrer la sortie et vérifier que `https://raw.githubusercontent.com/gfloxe/blixwou-launcher/main/appcast.xml` annonce X.Y.Z.
- Ne jamais lire, afficher, copier ni committer la clé privée. Transmettre uniquement son chemin au script de publication. Ne jamais modifier la clé publique de production `5Hju42KcDdq4t/Cu1yyrLnTBT/rwmkHemtn9XbsFZl8=`.
- Ne jamais modifier ou supprimer une Release existante ; ne jamais utiliser un push forcé. Préserver l’appcast publié lors de simples changements de code.
- Garder les projets de mods client et serveur séparés. Le mod blixwou-menu ne doit jamais aller sur exaroton.
- Les tests natifs WinSparkle utilisent uniquement une identité distincte, une clé jetable et un installateur témoin. Ne supprimer que les clés de registre de test créées par cet essai.
