# Publication du pack

`gfloxe/blixwou-distribution` est **une proposition de nom**, pas un dépôt existant. Aucun dépôt ni Release n’a été créé pendant cette réalisation.

## Première publication

1. Dans GitHub, connecté à `gfloxe`, créer un dépôt public nommé `blixwou-distribution` si ce nom est disponible. Un dépôt public permet le téléchargement sans embarquer de jeton privé.
2. Préparer localement un dossier `pack/` contenant seulement `mods/`, `config/`, `defaultconfigs/` et `resourcepacks/`. Exclure les sauvegardes, captures, `options.txt`, fichiers serveur secrets et tous les fichiers sans autorisation de redistribution.
3. Copier `distribution/pack-metadata.example.json` vers `pack-metadata.json`, **hors du dossier pack**. Renseigner la version exacte NeoForge relevée sur exaroton, la version de pack, l’adresse et les liens souhaités.
4. Déclarer chaque fichier dans `fileRules`. Le générateur refuse un fichier non déclaré ou dont l’autorisation n’est pas documentée.

Exemple de règle structurelle, à adapter à un vrai fichier autorisé :

```json
"fileRules": {
  "config/votre-configuration.json": {
    "side": "both",
    "policy": "seed",
    "redistributionAuthorized": true,
    "licenseOrPermission": "Configuration écrite par le propriétaire du serveur"
  }
}
```

`side` vaut `client`, `both` ou `server`. Les fichiers `server` figurent dans le manifeste pour l’inventaire mais ne sont jamais installés sur le client. **Ne publiez jamais de secrets serveur**, même avec `side: server`, car les assets GitHub sont publics. Vérifiez la documentation de chaque mod ; le launcher ne déduit pas automatiquement son côté.

`policy: enforced` restaure le fichier exact à chaque mise à jour. `policy: seed` ne crée une configuration que si elle manque, sans modifier une copie existante ni la supprimer plus tard. Une migration d’une configuration `seed` vers `enforced` bloque si le fichier existe : le joueur doit déplacer sa copie après lecture de vos instructions. Réservez `seed` aux fichiers de configuration, pas aux mods. Les paramètres imposés réellement sensibles doivent également être validés côté serveur.

5. Choisir un tag, par exemple `pack-0.1.0`, puis préparer la Release. L’URL ci-dessous désigne **votre future Release** : elle ne fonctionnera qu’une fois le dépôt et cette Release créés.

```powershell
.venv\Scripts\python.exe tools\prepare_pack.py --pack .\pack --metadata .\pack-metadata.json --output .\output\pack-0.1.0 --release-url 'https://github.com/gfloxe/blixwou-distribution/releases/download/pack-0.1.0'
```

Le dossier de sortie doit être vide et hors du pack. Le générateur produit `manifest.json`, `permissions.json` et `assets/` avec des noms basés sur SHA-256. Il n’envoie rien sur GitHub. Les fixtures `test.invalid` utilisées par les tests ne sont jamais des URL de distribution.

6. Créer une Release en brouillon portant exactement ce tag. Joindre tous les fichiers du dossier `assets/`, puis `manifest.json` et `permissions.json`. Publier la Release complète uniquement après téléversement de tous les fichiers. Ouvrir ensuite les liens pour vérifier qu’ils téléchargent réellement les bons fichiers.
7. Pour une adresse de manifeste stable, committer **une copie du manifeste validé** sous `channels/stable/manifest.json` dans la branche principale du dépôt. Le manifeste doit continuer de pointer vers les assets immuables de la Release précise. Renseigner l’adresse raw HTTPS de ce fichier dans `launcher-config.json`, seulement après avoir vérifié son existence. Ne jamais publier le manifeste stable avant ses assets.

Structure proposée du dépôt :

```text
README.md
channels/stable/manifest.json
pack-metadata.json
permissions/
  pack-0.1.0.json
# Fichiers lourds : assets des Releases GitHub, pas dans l’historique Git
```

Ne placez aucun jeton GitHub dans le code, dans un manifeste ou dans les fichiers du pack. Le propriétaire publie depuis GitHub ou depuis son propre `gh` authentifié localement.

## Versions suivantes

Modifier le dossier pack et ses règles, augmenter `packVersion`, utiliser un **nouveau** tag et un nouveau dossier de sortie. Générer, publier les assets puis le manifeste de la Release, tester avec une installation isolée, et finalement mettre à jour `channels/stable/manifest.json`.

Le launcher compare tailles et empreintes locales. Il ne retélécharge pas les fichiers corrects, même si une URL de Release a changé. Il reprend les fichiers `.part` quand le serveur accepte Range ; sinon il recommence ce téléchargement. Il ne bascule sur les nouveaux fichiers qu’après leur vérification. Il récupère la transaction après interruption. L’échec de la vérification du manifeste ou d’un téléchargement interdit le lancement jusqu’à réparation ; un cache ancien n’est pas présenté comme à jour.

La suppression concerne les anciens fichiers gérés absents du nouveau pack. Un mod imposé est supprimé même si son contenu a été modifié, conformément au choix du propriétaire de synchroniser strictement les mods ; cela évite de conserver une ancienne version lors d’un changement de nom. Les autres fichiers imposés obsolètes ne sont supprimés que si leur empreinte est inchangée. Les fichiers personnels non gérés, les configurations `seed`, les captures et les mondes sont conservés.

Pour revenir à une version antérieure, republier le manifeste stable pointant vers ses assets encore disponibles. Il n’y a pas de sélection de serveurs ni de versions dans l’interface des joueurs.

Le manifeste est obtenu via HTTPS depuis le dépôt du propriétaire ; ses empreintes assurent l’intégrité des fichiers, **pas** la sécurité d’un compte GitHub compromis. Protéger le compte et la branche de distribution. Les signatures des mises à jour du launcher relèvent d’un mécanisme séparé décrit dans `LAUNCHER-UPDATES.md`.
