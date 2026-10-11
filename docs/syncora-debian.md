# Syncora sur Debian

Circuit : Syncora → pack Debian → launcher. GitHub est une copie de secours,
actualisée toutes les minutes à partir du manifeste Debian. Une publication
GitHub utilise un seul commit, sans push forcé ni release du launcher.
Le timer historique d’import GitHub ne modifie plus le pack quand `pack/primary`
existe. Les fichiers remplacés restent stockés par SHA256 pour les téléchargements
déjà commencés. Leur nettoyage n’est pas automatique.

## Dossiers

- `/home/alex/Syncora/web` : interface compilée, seuls fichiers servis au navigateur.
- `/home/alex/Syncora/private` : base SQLite administrateur, historique, sessions,
  jeton GitHub et état de sauvegarde. Permissions 700/600, jamais servis par HTTP.
- `/home/alex/Syncora/source` : archives de déploiement publiques.
- `/home/alex/Syncora/backups` : copie des anciens fichiers serveur avant déploiement.
- `/home/alex/BLIXWOU-Services/services` : backend Python maintenu avec la passerelle.
- `/home/alex/BLIXWOU-Services/pack` : manifeste atomique et objets adressés par hash.
- `/home/alex/BLIXWOU-Services/private` : clés exaroton et publication interne.

Le service utilisateur `blixwou-server-gateway` sert l’interface sous `/syncora/`,
sur le Funnel HTTPS existant : https://debian-machine.tail7d0337.ts.net:8443/syncora/
Il démarre automatiquement, avec le timer `blixwou-pack-backup.timer`.

## Administrateur

Création ou réinitialisation depuis SSH, sans communiquer le mot de passe :

```sh
cd /home/alex/BLIXWOU-Services
.venv/bin/python -m services.syncora_admin
```

Un seul administrateur, aucune inscription publique. Mot de passe haché avec
scrypt et sel individuel. Cookies Secure/HttpOnly/SameSite=Strict, sessions 8 h,
limite 10 essais/10 min, contrôle Origin pour toutes les mutations. La commande
révoque les anciennes sessions. Les mots de passe ne sont jamais envoyés à GitHub.
Le jeton GitHub de sauvegarde doit rester dans `Syncora/private/github.token`;
préférer un jeton limité au dépôt gfloxe/BLIXWOU, permission Contents write.

## Utilisation

La destination Debian remplace l’ancienne destination GitHub. Choisir `mods`,
`shaderpacks` ou `resourcepacks` dans les paramètres. Seuls les JAR (mods) et ZIP
(packs) jusqu’à 50 Mo sont acceptés. Un fichier existant conserve son côté
client/serveur. Un nouveau mod envoyé aussi à exaroton est marqué `both`.
Le menu BLIXWOU est refusé sur exaroton. Les choix et le serveur visible sont
locaux au navigateur; l’API n’autorise que le serveur configuré sur Debian.
La comparaison exaroton utilise la taille : elle n’est pas une preuve de hash.
L’étiquette GitHub secours affiche l’état réel de la dernière sauvegarde.

Le launcher utilise son miroir Debian principal et GitHub si Debian ne répond
pas. Les fichiers téléchargés sont vérifiés par leur hash de contenu (SHA256),
mais le manifeste n’a pas de signature cryptographique indépendante.
Une release du launcher reste une opération distincte, jamais déclenchée par Syncora.

## Construction

Sources UI : `syncora-web/`. Depuis ce dossier : `npm ci`, puis `npm run build`.
Copier uniquement `dist/` dans le dossier `web` de Debian. Ne jamais y copier
les sources privées, les fichiers .env ni les bases de données.
Backend : modules `services/syncora_admin.py`, `pack_publish.py`, `pack_backup.py`.
Tests : `python -m pytest`. Journaux :

```sh
journalctl --user -u blixwou-server-gateway -u blixwou-pack-backup --no-pager
```

