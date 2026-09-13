# Mises à jour du launcher

Le dépôt unique gfloxe/blixwou-launcher contient le code et le flux appcast.xml. Pousser du code ne modifie pas les joueurs. La clé publique et l’AppId sont fixes. Les Releases existantes ne sont jamais remplacées.

## Démarrage

Avant la synchronisation du pack, le launcher lit le flux via network.py (timeout réseau 5 secondes, taille bornée), compare numériquement X.Y.Z et ignore silencieusement un flux absent, invalide ou inaccessible. Si une version supérieure est disponible, il bloque Jouer et la synchronisation, affiche sa progression puis appelle WinSparkle check_update_with_ui_and_install. Les vérifications automatiques périodiques natives sont désactivées. WinSparkle contrôle la signature Ed25519 avant d’exécuter l’installateur. En cas d’erreur ou d’annulation, un message discret apparaît et le fonctionnement normal reprend.

Les callbacks empêchent un arrêt pendant une partie ou une synchronisation. L’installateur silencieux relance BLIXWOU via WizardSilent ; le chemin interactif conserve la case Ouvrir BLIXWOU. Aucune donnée joueur n’est supprimée.

## Préparer sans publier

```powershell
.\tools\release.ps1 -Version 0.1.2 -PrivateKeyFile 'C:\chemin-prive\blixwou-update.key' -DryRun
```

Le dépôt doit être propre sur main, GitHub CLI connecté, et git pull --ff-only doit réussir. Les tests passent avant puis pendant le build. Le script signe et vérifie le nouvel installateur, écrit output/appcast-0.1.2.xml et output/appcast.xml, puis restaure les versions sources. Aucun commit, tag, push ou Release en DryRun. PublicKeyOverride reste réservé aux essais avec une clé jetable ; ne pas distribuer leur appcast.

## Publication explicite

Même commande sans -DryRun, seulement sur demande explicite. L’ordre est : version source, build, signature et vérification, génération de l’appcast candidat, commit Version X.Y.Z, tag, push atomique de main et du tag, création de Release avec --verify-tag, vérification des octets téléchargés depuis GitHub, puis seulement commit et push de l’appcast. L’ancien appcast reste inchangé jusque-là.

En cas d’échec avant le push, les versions et le commit local de préparation sont annulés. L’ordre demandé implique que le code et le tag sont déjà publics avant la création de Release : il est donc impossible de garantir « rien publié » si cette dernière échoue après le push. Le script tente alors un commit de retour de version et retire uniquement son nouveau tag, sans push forcé et sans toucher à une Release. Si l’état distant est incertain, il conserve les références et demande de vérifier GitHub. Les joueurs restent sur l’ancien appcast.

Si la Release existe mais que l’appcast n’est pas publié :

```powershell
.\tools\release.ps1 -Version 0.1.2 -ResumeAppcast
```

Conserver output/appcast-0.1.2.xml et l’installateur correspondant. Cette reprise ne signe ni ne recrée la Release : elle vérifie la signature et le fichier réellement publié avant de pousser le flux. Seule une modification en attente de appcast.xml est tolérée ; les autres modifications doivent être commitées. Une divergence Git doit être résolue avant la reprise. Un appcast plus ancien ne peut pas remplacer une version plus récente.

## Tests natifs isolés

```powershell
.venv\Scripts\python.exe tools\test_update_e2e.py
```

Le test construit un petit exécutable témoin avec le compilateur .NET présent dans Windows, utilise une clé jetable hors du dossier HTTP public et une identité de registre unique. Aucun clic n’est envoyé. Le flux HTTP local est accepté par WinSparkle ; seule cette procédure de test autorise HTTP, le launcher conserve HTTPS obligatoire.

Résultat du 13 septembre 2026 : même version ignorée (aucun témoin), nouvelle version installée sans clic (témoin créé, callback shutdown), signature altérée refusée (callback error, aucun témoin). Les seules clés de registre de test sont supprimées. Les résultats sont dans output/update-e2e-results.json.

Ce test prouve le lancement automatique d’un installateur signé. Il ne remplace pas le test d’une vraie migration BLIXWOU 0.1.1 vers 0.1.2, de la relance Inno et de la conservation des données pendant cette migration. La 0.1.2 n’est pas publiée par ces travaux.

Les joueurs en 0.1.0 doivent installer manuellement la première version configurée. La version 0.1.1 possède encore l’ancien mécanisme de vérification. Le comportement automatique décrit ici sera embarqué dans une future version. L’installateur n’est pas signé Authenticode : SmartScreen peut afficher un avertissement ; Ed25519 est une protection distincte.
