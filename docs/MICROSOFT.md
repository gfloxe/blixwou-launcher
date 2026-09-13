# Application Microsoft et comptes

Le code réalise un flux **client public de bureau** avec navigateur système, code d’autorisation, PKCE/S256 et `state`. Aucune page du launcher ne reçoit le mot de passe Microsoft. Le code ne contient pas d’identifiant emprunté à un launcher tiers ni de client secret.

## Prérequis du propriétaire

L’application BLIXWOU a depuis été inscrite par le propriétaire. Son ID client public `75252e49-3786-474f-ae9d-214ff6191ce9` est intégré à `launcher-config.json`. Le retour attendu reste `http://localhost:8765/callback`. Les ID d’objet et de répertoire ne sont pas nécessaires au flux personnel `consumers`. La connexion réelle et l’autorisation des API Minecraft restent à vérifier ; aucun secret client n’est requis.

### Vérification du portail le 12 septembre 2026

Le portail Entra ouvert sur le PC reconnaît le compte personnel, mais affiche `AADSTS16000` : ce compte n’existe pas dans le répertoire sélectionné `Microsoft Services`. Aucun identifiant d’application BLIXWOU n’a pu être créé. Il faut accéder à un répertoire Entra dont le compte est membre et autorisé à inscrire des applications. Si aucun répertoire n’existe, suivre la [procédure Microsoft de création d’un environnement Entra](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-create-new-tenant), qui propose notamment l’inscription Azure. La connexion et les vérifications personnelles doivent être effectuées par le propriétaire. Cette erreur du portail ne démontre aucun problème avec la licence Minecraft du compte.

### Configuration à effectuer après obtention de l’accès

1. Enregistrer votre propre application dans Microsoft Entra ID. Autoriser les comptes Microsoft personnels ; le launcher utilise l’autorité `consumers`.
2. Configurer une plateforme **applications mobiles et de bureau**, avec le retour `http://localhost:8765/callback`, exactement comme `microsoft.redirectUri`. Activer l’utilisation comme client public. Ne pas enregistrer ce retour comme application Web confidentielle ou SPA.
3. Reporter l’ID d’application public dans `microsoft.clientId`. Aucun secret client n’est nécessaire ni approprié à un exécutable redistribuable.
4. Le code demande `XboxLive.signin offline_access`. **Une inscription Entra seule ne garantit pas l’accès aux API Minecraft/Xbox.** Obtenir l’autorisation de Microsoft/Mojang applicable à votre application. Consulter les informations officielles [AppRegInfo](https://aka.ms/AppRegInfo) et les exigences en vigueur ; un rejet 403 doit être résolu avec Microsoft, pas contourné avec un ID emprunté.
5. Tester le consentement avec un compte personnel disposant de Minecraft Java et d’un profil Xbox, puis le renouvellement de session après redémarrage du launcher. Les restrictions parentales ou de compte Xbox peuvent aussi bloquer la connexion.

La [documentation du moteur Minecraft utilisé](https://minecraft-launcher-lib.readthedocs.io/en/stable/tutorial/microsoft_login.html) décrit l’obligation de demander l’accès Minecraft pour les nouvelles applications. Sa section historique mentionnant un secret ne correspond pas à notre implémentation : le protocole actuel employé ici est celui d’un client public avec PKCE, conformément à la [documentation Microsoft OAuth](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

## Parcours du joueur

Cliquer sur le profil puis « Se connecter avec Microsoft ». Le navigateur ouvre Microsoft. Un serveur HTTP temporaire n’écoute que sur `127.0.0.1`, vérifie le chemin et `state`, puis se ferme. Le délai est de trois minutes ; une fermeture demandée au launcher annule l’attente. La connexion passe ensuite par Xbox Live, XSTS et Minecraft Services. Les droits `game_minecraft`/`product_minecraft` puis le profil Java sont vérifiés avant de sauvegarder la session.

Le refresh token est chiffré par **Windows DPAPI, CurrentUser** dans `account.dpapi`. Il ne peut pas être déchiffré simplement en copiant ce fichier sous un autre utilisateur. Les jetons de jeu restent en mémoire ; ils sont renouvelés et les droits sont revérifiés avant chaque lancement Microsoft, après les téléchargements. Le refresh token tournant est enregistré même si le service Minecraft est temporairement indisponible. Les logs du launcher ne contiennent ni corps OAuth ni commande de lancement. « Déconnecter le profil » efface les secrets locaux ; la révocation du consentement se fait également dans le compte Microsoft.

DPAPI protège le stockage au repos. Comme avec les launchers Java classiques, les arguments de processus requis par Minecraft peuvent être lus par des processus suffisamment privilégiés sur la même machine. Ne publiez pas aveuglément les rapports de crash produits par des mods tiers ; leur contenu n’est pas contrôlé par le launcher.

## Profils hors ligne et serveur

Le profil hors ligne possède un pseudo validé, un UUID dérivé de `OfflinePlayer:<pseudo>`, un jeton nul et le type `legacy`. Il ne présente aucun droit Microsoft et n’est jamais transformé automatiquement en profil Microsoft après un échec de connexion. Aucun résultat Microsoft inventé n’est utilisé.

Le serveur doit gérer la réservation des pseudos, l’authentification des joueurs hors ligne, l’association éventuelle des comptes et les permissions. Le launcher ne peut pas empêcher un autre client de présenter le même pseudo à un serveur acceptant les connexions hors ligne. Ne désactivez aucune protection du serveur sur la foi d’une vérification locale du launcher.

**Non testé avec un compte réel à la livraison** : aucun client ID autorisé n’a été fourni, aucun compte ni mot de passe n’a été demandé. Les tests couvrent le chiffrement Windows et le refus d’un compte sans droits Java ; le parcours externe reste à valider avec votre application approuvée.
