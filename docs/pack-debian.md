# Pack Debian

La source principale est maintenant Syncora, hébergé sur Debian.
Voir [Syncora Debian](syncora-debian.md) pour l’administration, les dossiers,
la publication et la copie GitHub automatique.

Le launcher télécharge `/pack/manifest.json` puis les objets SHA256 du miroir.
En cas d’indisponibilité, il consulte le manifeste GitHub. Les fichiers de secours
sont toujours vérifiés avec la taille et le SHA256 attendus.

Le timer historique `blixwou-pack-mirror.timer` reste installé pour le bootstrap,
mais n’importe plus GitHub quand le marqueur `pack/primary` existe. Pour restaurer
volontairement une copie GitHub, arrêter les écritures Syncora et sauvegarder le
pack avant de retirer ce marqueur; ce n’est pas le mode de fonctionnement normal.
