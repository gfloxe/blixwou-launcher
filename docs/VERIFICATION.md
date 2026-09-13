# Vérifications de livraison

## Vérifications réalisées

- Métadonnées Mojang obtenues par HTTPS : Minecraft **1.21.10**, Java **21**, présence des arguments Quick Play multijoueur. Résultat reproductible dans `compatibility-verified.json`.
- Catalogue NeoForge : **63 entrées de la branche 21.10** observées lors de la consultation. Le champ de version du serveur reste `null` ; Minecraft n’a pas été changé.
- Téléchargement réel du JDK Eclipse Temurin 21 x64, vérification SHA-256, extraction puis exécution de Java avec validation du numéro majeur et de l’architecture.
- Téléchargement réel et vérification SHA-256 de l’installateur officiel **21.10.64**, utilisé uniquement comme artefact de test. Son `install_profile.json` confirme Minecraft 1.21.10. Ce test ne sélectionne pas la version du serveur.
- Tests automatisés de chemins Windows dangereux, doublons de casse, mauvaise version, SHA-256 invalide, reprise HTTP Range, conservation des fichiers actifs en cas de corruption, mise à jour différentielle, fichiers serveur exclus, configurations initiales préservées, conflits de fichiers personnels, suppressions limitées et récupération transactionnelle.
- Tests du refus d’un compte Microsoft sans droits Minecraft Java, de l’UUID hors ligne et de **DPAPI Windows réel**, dont un chiffré volontairement altéré.
- Test protocolaire du statut serveur ; différenciation entre délai réseau et refus de connexion. L’interrogation réelle de `BLIXWOU.exaroton.me:48255` a retourné **Indisponible** depuis cette machine. Ce résultat ne prouve pas un arrêt du serveur.
- Test des arguments du jeu : dossier dédié, RAM, identité hors ligne séparée et cible Quick Play. Test réel du suivi d’un processus Windows et du déverrouillage après sa terminaison.
- Test Qt des profils, de l’enregistrement des paramètres et du masquage des liens sociaux vides. Rendu de l’interface inspecté visuellement dans `output/preview.png`.
- WinSparkle 0.9.4 x64 téléchargé avec archive vérifiée SHA-256. Test avec **clé jetable** : signature acceptée pour le fichier original, refusée après modification ; chargement de la DLL et validation de la clé publique réussis. Aucune clé de publication de production créée.
- Inno Setup 6.7.3 obtenu depuis la Release officielle, SHA-256 vérifié, signature Authenticode **Pyrsys B.V. valide** avant installation de l’outil de compilation dans `vendor/inno`.

Les résultats finaux de compilation et d’installation isolée sont consignés dans `BUILD-RESULTS.md` après exécution. Une réussite des tests ne signifie pas qu’une session Microsoft réelle ou qu’une connexion avec votre modpack a été validée.

## Reproduire

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe tools\verify_compatibility.py
.venv\Scripts\python.exe run.py --screenshot .\output\preview.png --data-dir .\output\preview-data --no-network
```

`tools/integration_probe.py` télécharge Java et vérifie un installateur NeoForge depuis le catalogue officiel sans modifier la configuration de production. `tools/smoke_install.py --neoforge <version-de-test> --java <java.exe>` effectue une installation officielle dans `output/integration-install`, génère les arguments, mais ne lance pas le jeu.

Les premiers essais pytest dans le bac à sable ont rencontré un refus d’accès aux dossiers temporaires Windows. Les mêmes tests ont été exécutés ensuite avec les autorisations adaptées, dans le dossier de projet. Aucun résultat de test en échec n’a été masqué comme réussi.

## Informations restant à fournir

1. **Numéro exact NeoForge du serveur** (`21.10.x`, suffixe `-beta` éventuel), relevé sur exaroton. La confirmation reçue de Minecraft 1.21.10 ne fournit pas ce numéro.
2. **Pack autorisé** : liste/fichiers de mods client, communs et serveur, configurations imposées ou initiales, resource packs et autorisations de redistribution.
3. **Application Microsoft approuvée** : son client ID public et le retour enregistré. L’accès Minecraft/Xbox de l’application doit être effectif.
4. **Dépôt de distribution créé**, assets et manifeste publiés ; son URL doit être insérée dans la configuration.
5. **Liens sociaux**, facultatifs ; ils sont actuellement masqués.
6. **Clé publique WinSparkle et appcast publié**, puis certificat Authenticode si vous souhaitez une signature d’éditeur Windows reconnue.

## Recette avec le propriétaire avant diffusion aux joueurs

- Installer une première fois depuis une session Windows x64 ordinaire, avec un nouveau dossier BLIXWOU.
- Tester la connexion Microsoft complète avec un compte possédant Minecraft Java, puis fermer/rouvrir et vérifier le renouvellement. Tester également un refus de consentement et un accès Java manquant.
- Tester un profil hors ligne sur le serveur, puis la réservation des pseudos et la coexistence des identités selon votre configuration côté serveur.
- Vérifier que le pack correspond exactement à NeoForge et à la liste de mods du serveur ; effectuer la connexion Quick Play réelle.
- Publier deux versions de pack autorisées et vérifier les migrations de configuration. Tester la restauration après coupure d’un téléchargement et la préservation des fichiers personnels.
- Effectuer une mise à jour WinSparkle entre deux versions de launcher réellement publiées avec la clé du propriétaire ; vérifier le comportement de l’installateur et la conservation des données à la désinstallation.

**Limites explicites** : aucune publication GitHub, aucune utilisation d’un compte Microsoft réel, aucune connexion Minecraft au serveur et aucun essai du modpack propriétaire n’ont été effectués. Les changements de schéma, de Minecraft ou de versions majeures de Java nécessitent une nouvelle édition du launcher, pas une migration silencieuse.
