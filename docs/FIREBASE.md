# Comptes communautaires Firebase

Le bouton **Compte BLIXWOU** ouvre l'inscription, la connexion, la réservation du
pseudo et la récupération de mot de passe. Il ne modifie pas les profils Minecraft,
les licences, la garde-robe, ni les sessions du serveur de jeu.

La configuration publique du projet `blixwou` est dans `launcher-config.json`.
La clé Web Firebase n'est pas une clé d'administration. Aucun compte de service ni
clé exaroton ne doit être ajouté au launcher. Analytics n'est pas intégré.

## Configuration administrateur

1. Firebase Authentication → Mode de connexion : activer E-mail/Mot de passe.
2. Firestore : vérifier que la base `(default)` existe en mode natif.
3. Lire les règles existantes avant tout remplacement : si d'autres applications
   utilisent la base, fusionner les règles au lieu d'écraser leurs collections.
4. Publier les règles fournies dans `firebase/firestore.rules` depuis la console
   ou, avec une CLI Firebase déjà authentifiée, depuis le dossier `firebase` :
   `firebase deploy --project blixwou --only firestore:rules`.
5. Vérifier les règles avec deux comptes de test : profils privés, noms uniques,
   refus des écritures inter-comptes, refus de modifier les réservations et les bans.

Ne pas utiliser le mode test ouvert de Firestore. Les règles du dépôt ne sont pas
automatiquement déployées par un push GitHub ni par une Release du launcher.

## Données et limites

- Authentication conserve les identifiants et mots de passe. Aucun mot de passe
  n'est écrit dans Firestore, les fichiers du launcher ou ses journaux.
- `users/{uid}` contient `username` et `createdAt`, lisibles seulement par ce compte.
- `usernames/{pseudo}` contient `uid` et `createdAt`. Le nom est normalisé en minuscules.
  Les deux documents sont créés atomiquement, avec une précondition d'absence et
  des validations réciproques `getAfter`. Un compte ne peut réserver qu'un pseudo.
- `bans/{uid}` : la présence du document bloque le compte dans les règles.
  Seul l'administrateur peut créer/supprimer ce document depuis la console.
  Cela ne constitue pas encore un ban Minecraft ou un ban IP du serveur exaroton.
- Les jetons sont conservés dans `firebase-account.dpapi`, chiffré pour l'utilisateur
  Windows. Déconnexion : suppression de cette session locale uniquement.
- Le compte Auth est conservé si la réservation échoue (pseudo pris ou Firestore
  indisponible). Après connexion, « Valider mon pseudo » permet de terminer.
- Pas de renommage, de suppression de compte ni de collecte d'IP côté Firebase
  dans cette première intégration. Pas de migration automatique des comptes SQLite.

## Vérifications

`python -m pytest` couvre les erreurs réseau, la réservation atomique côté client,
le renouvellement des jetons, l'isolation des sessions Minecraft, les bans et le dialogue.
Les tests simulent Firebase : ils ne remplacent pas un test des règles dans l'émulateur
ou le projet de test. Aucun e-mail de test n'est envoyé par cette suite.

Références :
- https://firebase.google.com/docs/reference/rest/auth
- https://firebase.google.com/docs/firestore/use-rest-api
- https://firebase.google.com/docs/firestore/security/rules-conditions

## exaroton reste sur Debian

Le refus HTTP 403 de la clé fournie doit être résolu côté exaroton. Une clé privée ne
doit pas être collée dans le chat. Révoquer celle partagée et créer une nouvelle clé,
puis la saisir directement dans la session SSH :

```sh
cd /home/alex/BLIXWOU-Services
.venv/bin/python -m services.configure_exaroton
```

La saisie est masquée ; le fichier privé n'est écrit qu'après validation du serveur.
Le service Debian reste sur `127.0.0.1:8766`. Son accès HTTPS public et le raccordement
du statut au launcher restent à configurer. Firebase Authentication n'expose pas ce service.
