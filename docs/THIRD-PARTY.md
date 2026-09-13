# Provenance, licences et compatibilité

## Sources consultées

- [Mojang — catalogue officiel](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json) : Minecraft 1.21.10, Java 21, arguments Quick Play. Le résultat de consultation est enregistré dans `compatibility-verified.json` ; réexécuter `tools/verify_compatibility.py` pour une lecture actualisée.
- [NeoForge — documentation 1.21.10](https://docs.neoforged.net/docs/1.21.10/gettingstarted/) : Java 21 et JVM 64 bits.
- [NeoForge — catalogue officiel](https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge) : présence de la branche 21.10. Le numéro exact du serveur reste à fournir.
- [Adoptium — API](https://api.adoptium.net/) : distribution Eclipse Temurin Java 21 x64, lien officiel et empreinte SHA-256 fournis par le catalogue. Aucun JDK n’est redistribué dans le launcher ; ses fichiers de licence sont conservés dans l’archive extraite chez le joueur.
- [minecraft-launcher-lib — installation](https://minecraft-launcher-lib.readthedocs.io/en/stable/tutorial/getting_started.html) et [mod loaders](https://minecraft-launcher-lib.readthedocs.io/en/stable/modules/mod_loader.html) : version 8.0 inspectée localement.
- [Microsoft — OAuth avec PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow) et [informations d’enregistrement Minecraft](https://aka.ms/AppRegInfo).
- [WinSparkle — intégration](https://winsparkle.org/guides/integrating-winsparkle/) et [Release 0.9.4](https://github.com/vslavik/winsparkle/releases/tag/v0.9.4).
- [Inno Setup — téléchargement et éditeur](https://jrsoftware.org/isdl.php). L’outil utilisé pour la compilation locale est Inno Setup 6.7.3, téléchargé depuis la Release officielle, vérifié SHA-256 et signé Authenticode par Pyrsys B.V. Le compilateur n’est pas inclus dans le launcher.

## Composants redistribués

Python est embarqué par PyInstaller sous ses licences PSF. `minecraft-launcher-lib` utilise BSD-2-Clause ; requests Apache-2.0 ; urllib3 MIT ; certifi MPL-2.0 ; idna BSD-3-Clause ; charset-normalizer MIT. WinSparkle est sous licence MIT avec ses notices associées, conservées dans `vendor/COPYING` et `vendor/COPYING.expat`.

PySide6/Qt/Shiboken sont utilisés dans leur distribution open source, avec les obligations LGPL/GPL applicables à chaque composant. Seuls QtCore, QtGui et QtWidgets sont importés ; les notices fournies par les wheels sont recopiées sous `docs/licenses/`. L’application est distribuée en mode **onedir**, avec les DLL Qt séparées et remplaçables ; ne pas interdire le remplacement des bibliothèques ou la rétro-ingénierie nécessaire à ce remplacement. Les sources correspondantes de Qt/PySide sont disponibles auprès du [Qt Project](https://download.qt.io/official_releases/QtForPython/) pour la version 6.11.2 ; conserver les avis et fournir les sources/une offre conforme avant redistribution selon les termes précis des licences. Le code Python du launcher est livré au propriétaire.

`tools/collect_licenses.py` collecte les textes présents dans les dépendances installées pour les inclure dans le build. La licence de chaque mod ou resource pack doit être vérifiée séparément : aucun mod n’a été fourni ou ajouté par défaut. Les autorisations sont documentées par le propriétaire dans `fileRules`.

Les polices Segoe UI et Bahnschrift sont chargées depuis Windows et ne sont pas redistribuées. L’icône BLIXWOU est dessinée par `tools/create_icon.py`. Le paysage a été créé avec l’outil imagegen intégré, puis copié dans `assets/landscape.png` ; ce n’est pas une capture ni une texture propriétaire extraite du jeu. Prompt conservé dans `ASSET-PROMPT.md`.

BLIXWOU est un launcher indépendant ; aucune affiliation officielle avec Mojang, Microsoft ou NeoForged n’est revendiquée.
