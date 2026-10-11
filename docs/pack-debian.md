# Source de synchronisation Debian

Le launcher utilise en priorité `https://debian-machine.tail7d0337.ts.net:8443/pack/manifest.json`.
GitHub reste la source de publication du pack et le secours réseau du launcher.
Cette configuration concerne le pack (mods, configurations, textures, shaders), pas les mises à jour de l'exécutable.

Sur Debian, `/home/alex/BLIXWOU-Services/pack` contient le manifeste et les objets identifiés par SHA-256.
Le timer utilisateur `blixwou-pack-mirror.timer` démarre après le boot puis rafraîchit le miroir toutes les 60 secondes après la fin du précédent passage.
Il conserve le manifeste précédent en cas d'échec et ne publie le nouveau qu'après vérification de tous les fichiers.
Les anciennes empreintes restent disponibles pour les téléchargements en cours ; surveiller l'espace disque à long terme.

La passerelle publique expose uniquement le manifeste et les objets dont le nom est une empreinte hexadécimale.
Elle ne donne accès ni aux comptes ni au répertoire privé contenant les secrets.
Le launcher vérifie les mêmes tailles et SHA-256 pour Debian et pour le secours GitHub.

Diagnostic sans sudo :

```sh
systemctl --user status blixwou-pack-mirror.timer
journalctl --user -u blixwou-pack-mirror.service -n 20
systemctl --user start blixwou-pack-mirror.service
```

Les services restent activables au démarrage grâce à `Linger=yes` pour alex.
Les launchers déjà installés restent sur GitHub tant qu'une nouvelle version n'est pas publiée.
