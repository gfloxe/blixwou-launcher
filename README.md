# BLIXWOU — launcher Minecraft Java pour Windows x64

Application native en français, exclusivement configurée pour `BLIXWOU.exaroton.me:48255`. Le projet contient l’interface Qt, l’installation réelle de Minecraft/NeoForge/Java, les profils Microsoft et hors ligne, la mise à jour du pack, WinSparkle et le script d’installateur Inno Setup.

**Migration Minecraft 1.21.1 / NeoForge 21.1.250.** Le launcher utilise Java 21 et synchronise le pack GitHub à chaque lancement. Le dépôt doit publier un manifeste correspondant à cette version. La connexion Microsoft reste soumise à l’approbation de l’application par Minecraft Services.

## Ouvrir l’application

Après construction, double-cliquer sur `dist/BLIXWOU/BLIXWOU.exe`. Conserver le dossier `_internal` à côté de l’exécutable. L’installateur est produit dans `dist/installer/`.

Pour développer avec Python **3.12 x64**, dans PowerShell depuis ce dossier :

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe run.py
```

Les utilisateurs finaux n’ont pas besoin d’installer Python. L’installation par défaut n’exige pas de droits administrateur. Le dossier de données est `%LOCALAPPDATA%\BLIXWOU`, distinct de l’installation habituelle `.minecraft`.

## Configuration du propriétaire

Le fichier central est `launcher-config.json`. En développement il est à la racine ; dans l’exécutable empaqueté il se trouve dans `_internal`. Modifier le fichier source puis reconstruire pour distribuer une configuration cohérente.

| Champ | À fournir |
|---|---|
| `manifestUrl` | URL HTTPS du manifeste effectivement publié |
| `neoforge` | Numéro du serveur, de la forme `21.1.x`, si vous souhaitez aussi le consigner localement |
| `microsoft.clientId` | ID public de votre propre application Microsoft autorisée |
| `microsoft.redirectUri` | Retour enregistré : `http://localhost:8765/callback` |
| `socials` | Liens HTTPS ; laisser `null` pour masquer une icône |
| `launcherUpdate.appcastUrl` | URL HTTPS du flux des versions du launcher |
| `launcherUpdate.ed25519PublicKey` | Clé publique de signature WinSparkle, jamais la clé privée |

Les versions du pack publié et l’adresse du serveur sont autoritatives dans son manifeste. Le champ local `neoforge` sert de référence au contrôle de publication ; il ne choisit pas automatiquement une version et ne remplace pas un manifeste. Minecraft reste strictement `1.21.1`, Java `21` ; le runtime vérifie aussi le catalogue Mojang, l’existence de NeoForge et le `minecraft` de l’installateur officiel.

**Un numéro Minecraft n’est pas un numéro NeoForge.** La capture du serveur exaroton indique `1.21.1 (250)` sous NeoForge : les métadonnées d’exemple utilisent donc `21.1.250`, dont la cible a été vérifiée dans les métadonnées de l’installateur officiel.

## Construire l’exécutable et l’installateur

```powershell
# Exécutable portable + tests + dépendance WinSparkle officielle vérifiée
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1

# Installer Inno Setup 6 depuis son site officiel, puis :
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1 -Installer

# Chemin du compilateur personnalisé :
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1 -Installer -InnoCompiler 'C:\chemin\ISCC.exe'

# Avant une publication destinée aux joueurs :
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1 -Installer -Release
```

Le mode `-Release` exige les paramètres de distribution, Microsoft et signature manquants. Une compilation de développement les laisse explicitement désactivés. Le workflow GitHub Actions fourni construit des **artefacts de développement**, sans les publier automatiquement.

La version de l’application doit être mise à jour ensemble dans `pyproject.toml`, `blixwou/__init__.py`, `launcher-config.json`, `minecraft.py` (identification du launcher) et `installer/BLIXWOU.iss`. Une nouvelle version du pack ne nécessite pas de reconstruire le launcher tant que son schéma et Minecraft restent compatibles.

## Fonctionnement et choix techniques

- Python 3.12 + PySide6/Qt : interface native, tâches réseau hors du thread graphique et code maintenable. PyInstaller embarque Python et Qt pour les joueurs.
- `minecraft-launcher-lib` 8.0 : résolution des bibliothèques, ressources, règles et arguments Minecraft. Son téléchargement est adapté dans un module isolé pour assurer HTTPS, empreintes et remplacement atomique. NeoForge est installé par son propre JAR officiel.
- Java : Eclipse Temurin 21 x64 depuis l’API Adoptium, archive vérifiée SHA-256 avant extraction. Le Java personnalisé doit être un exécutable Java 21 64 bits valide.
- Microsoft : navigateur système, OAuth avec PKCE/S256 et `state`, Xbox Live/XSTS, Minecraft Services, vérification des droits Java puis du profil. Renouvellement juste avant le lancement ; refresh token chiffré avec DPAPI lié à l’utilisateur Windows. Aucun mot de passe ni client secret demandé.
- Hors ligne : UUID `OfflinePlayer:<pseudo>`, jeton nul et type `legacy`. Aucune fausse identité Microsoft. La coexistence des profils et la protection des pseudos sont à mettre en œuvre côté serveur.
- Statut : Server List Ping direct, toutes les 30 secondes. Une réponse protocolaire donne « En ligne », un refus de connexion « Hors ligne », un délai/DNS/réponse illisible « Indisponible ». Une réponse de proxy décrit ce point d’entrée, pas une garantie que l’authentification et tous les mods fonctionneront.
- Pack : comparaison SHA-256 et réparation à chaque démarrage et avant Jouer. Fichiers temporaires vérifiés, sauvegardes de transaction, récupération après crash. Un fichier non géré en conflit bloque la mise à jour au lieu d’être écrasé. Les configurations `seed` sont conservées. Les anciens mods gérés retirés du manifeste sont supprimés, même modifiés, pour éviter les doublons ; les configurations et resourcepacks obsolètes modifiés restent préservés.
- Lancement : Quick Play multijoueur vers l’adresse du manifeste ; verrou interprocessus, bouton désactivé pendant les opérations et suivi du PID/date de création de Java après crash du launcher.
- Launcher : WinSparkle 0.9.4 x64, archive fournisseur épinglée SHA-256, mises à jour d’installateur authentifiées par Ed25519. La clé publique est embarquée. La signature Authenticode Windows est une étape de publication distincte.

## Dossiers et guides

```text
blixwou/              Interface et services du launcher
assets/               Paysage intégré et icône originale
launcher-config.json  Configuration du propriétaire
distribution/         Exemples sans fausses URL fonctionnelles
tools/                Préparation de pack, contrôles, signature/appcast, build
installer/            Installateur Inno Setup
tests/                Tests réseau, pack, comptes, processus et interface
docs/                 Guides et compte rendu des vérifications
```

Dans `%LOCALAPPDATA%\BLIXWOU` : `game/` contient le pack, les réglages du jeu, captures et sauvegardes ; `minecraft/` contient les ressources Mojang et bibliothèques NeoForge ; `runtime/` contient Java ; `logs/` contient les journaux. Les fichiers personnels sont préservés à la mise à jour et à la désinstallation du launcher. Les journaux propres à Minecraft sont dans `game/logs/`.

- [Créer le dépôt et publier le pack](docs/DISTRIBUTION.md)
- [Enregistrer l’application Microsoft](docs/MICROSOFT.md)
- [Publier une mise à jour signée du launcher](docs/LAUNCHER-UPDATES.md)
- [Vérifications et limites restantes](docs/VERIFICATION.md)
- [Sources et licences](docs/THIRD-PARTY.md)

Ce projet ne redistribue aucun JAR Minecraft, Java ni mod propriétaire. Les téléchargements du jeu sont effectués sur le poste du joueur depuis les sources officielles. Distribuer uniquement les mods et resource packs pour lesquels vous possédez les autorisations nécessaires.

## Télécharger

[Installer la dernière version publiée de BLIXWOU](https://github.com/gfloxe/blixwou-launcher/releases/latest).

Le code de main peut contenir des fonctionnalités en préparation. Seule une publication explicite met à jour les joueurs.
