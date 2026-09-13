# Résultats de construction Windows

## Synchronisation des shaders

Le launcher accepte maintenant `shaderpacks/` dans le manifeste. Les archives imposées sont vérifiées et réparées, les anciennes archives gérées retirées du pack sont supprimées. Les réglages `.txt` peuvent utiliser la politique `seed`, qui conserve les préférences du joueur. Le bouton des paramètres ouvre `game/shaderpacks`. Les 58 tests passent. Les versions locales du générateur et du workflow dans le dossier voisin `BLIXWOU-GitHub` sont mises à jour ; leur publication GitHub reste nécessaire avant que le manifeste distant inclue les shaders.

## Optimisation des ressources et du rendu

Le fond redimensionné est conservé en cache et recalculé seulement si la fenêtre change de taille. Benchmark local de 100 rendus 1120 × 700 : 340,2 ms avec redimensionnement systématique, 74,7 ms avec cache. Cette mesure porte uniquement sur le rendu du fond, pas sur la durée totale d’installation.

Les téléchargements publics utilisent désormais une session HTTP par thread pour réutiliser les connexions HTTPS. Les sessions ne sont pas partagées avec les requêtes OAuth ; les cookies sont vidés avant chaque téléchargement. Les huit téléchargements de ressources parallèles, les contrôles d’empreinte, la reprise et les écritures atomiques sont conservés. Le gain réseau réel dépend de la connexion et du serveur ; il n’a pas été chiffré. Les 57 tests passent, y compris le cache après redimensionnement et l’isolation des connexions entre threads.

## Connexion au dépôt publié

Le workflow GitHub 34694993852 a réussi. Le manifeste de gfloxe/BLIXWOU est intégré à la configuration. Le pack `024d11f4a4e44967a00c8e1e13ed6c86f0d943ff` a été synchronisé dans `output/published-pack-check` : 28 fichiers, 60 914 325 octets, empreintes vérifiées. Les métadonnées signalent deux JAR portant le modId ferritecore (8.0.2 et 8.1.0), ainsi qu’une dépendance obligatoire sodium pour Iris, absente des mods principaux publiés. Le jeu avec ce pack n’a pas été lancé ; ces problèmes doivent être corrigés sur GitHub. Les 55 tests du launcher passent (1,87 s). Les sections suivantes retracent les livraisons précédentes.

## Correction de la connexion et synchronisation des mods

55 tests passent (1,26 s) après ajout de la page HTML de retour Microsoft et des diagnostics OAuth/Xbox/Minecraft sans données sensibles. L’autorisation réelle du compte reste à tester avec les nouveaux messages. La page ne prétend pas que la connexion est terminée avant la vérification Minecraft. Son contrôle visuel automatique a été refusé par la politique du navigateur ; son contenu et son autonomie sont testés.

Le dossier voisin `BLIXWOU-GitHub` contient le dépôt de distribution prêt à publier, avec `mods/`, `server-mods/`, les réglages et GitHub Actions. Deux tests du générateur passent, dont une modification de contenu à taille identique. La création du dépôt distant est bloquée par la validation automatique du navigateur, même après accord explicite du propriétaire : aucun dépôt ni manifeste distant n’a été publié. La source reste sans URL de manifeste tant que la publication n’est pas vérifiée.

## Mise à jour Microsoft du 12 septembre 2026

L’ID client fourni par le propriétaire et NeoForge `21.10.64` sont intégrés à la nouvelle compilation. Les 48 tests passent (1,22 s), la compilation Inno Setup est terminée et le démarrage du binaire avec rendu local sans réseau retourne 0 (`output/preview-microsoft.png`). Le script PowerShell de compilation a aussi été corrigé pour accepter une apostrophe typographique dans son message d’erreur. La connexion Microsoft réelle et l’accès aux API Minecraft restent à valider. Les résultats ci-dessous décrivent la première livraison.

Environnement vérifié : **Windows 10 x64, build 19045**, Python **3.12.6**, PySide6 **6.11.2**, PyInstaller **6.22.2**, Inno Setup **6.7.3**. Le launcher et son installateur ciblent Windows 10 **1809 ou supérieur**, et Windows 11 x64.

- **48 tests automatisés passent.** Ils couvrent le pack, les téléchargements, les profils, DPAPI Windows, les processus, l’interface Qt, le générateur de manifeste et les signatures WinSparkle.
- **Installation officielle complète réussie** dans `output/integration-install` : Minecraft **1.21.10** et NeoForge **21.10.64**, choisi uniquement pour la validation isolée depuis le catalogue officiel. Les **4 403 ressources uniques** du jeu ont été téléchargées et vérifiées, les bibliothèques installées et l’installateur officiel NeoForge exécuté avec succès. Java 21 x64 provient du téléchargement Adoptium vérifié.
- **Deuxième passage réussi** sur l’installation existante : vérification des ressources et de l’inventaire NeoForge, puis génération complète des arguments avec Quick Play. Les deux paramètres modernes `clientid` et `auth_xuid` laissés intacts par launcher-lib 8.0 sont désormais remplis explicitement ou vides en mode hors ligne. Aucun paramètre `${…}` inconnu n’est transmis au jeu.
- **Jeu non lancé** pendant ce test ; aucune connexion Minecraft au serveur et aucun parcours Microsoft réel effectués.
- **Compilation de l’exécutable et de l’installateur Inno Setup réussie.** Cette compilation conservait NeoForge à `null`. Après la capture exaroton du propriétaire, les sources et exemples ont été mis à jour vers `21.10.64` le 12 septembre 2026 ; les exécutables et archives de cette compilation antérieure n’ont pas encore été régénérés. Le manifeste de production reste à définir.
- **Diagnostic du paquet effectué** : la DLL ICU d’une installation Git présente dans le PATH avait été collectée à tort. `tools/normalize_runtime.py` exclut cette DLL du paquet et conserve l’API ICU de Windows attendue par Qt. Le script harmonise aussi les runtimes Visual C++ embarqués avec ceux du wheel Qt. Il ne modifie aucune DLL système.
- **Démarrage du binaire final et rendu Qt réussis** après correction, code de sortie **0**. Capture inspectée : `output/preview-packaged.png`. Le binaire de diagnostic a également passé ce contrôle.

Le répertoire `output/` contient uniquement des essais locaux ; il est exclu de l’archive de sources et du launcher distribué. Les fichiers propriétaires téléchargés pour l’essai ne sont pas intégrés dans les livrables redistribuables. Les clés du test WinSparkle sont jetables et ne sont pas des clés de publication.

Les versions produites ici sont des **builds de développement non signés Authenticode**. Le mode `-Release` reste volontairement bloquant tant que l’URL du manifeste, l’application Microsoft, le flux WinSparkle et sa clé publique ne sont pas configurés.
