# Services privés BLIXWOU sur Debian

Installation : `/home/alex/BLIXWOU-Services`. Le service écoute **uniquement**
`127.0.0.1:8766`. Aucun port public, aucun changement Apache ni accès sudo automatique.
Le launcher distribué n'est pas encore raccordé : il faudra une URL HTTPS publique.
Ces comptes sont des comptes communautaires BLIXWOU, pas des licences Minecraft.
Les bans ci-dessous bloquent cette API, pas encore les connexions Minecraft sur exaroton.

## Installation sans sudo (après installation de python3-venv)

```sh
cd /home/alex/BLIXWOU-Services
python3 -m venv .venv
.venv/bin/python -m pip install -r services/requirements.txt
.venv/bin/python -m unittest services.test_api -v
mkdir -p ~/.config/systemd/user
cp services/blixwou-api.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now blixwou-api
curl http://127.0.0.1:8766/health
```

Le démarrage hors session utilisateur nécessite `sudo loginctl enable-linger alex`
(action manuelle de l'administrateur). Sans cela, la session utilisateur doit rester active.

## API

- `GET /health` : disponibilité du service.
- `GET /v1/server/status` : état exaroton, cache commun de cinq secondes, sans clé côté client.
- `POST /v1/server/start` : démarre le serveur s’il est éteint ; un verrou et un délai de 60 secondes évitent les demandes simultanées. Les autres joueurs observent le même démarrage. Cette route doit être publiée uniquement avec les limites d’accès et la protection réseau prévues pour le jeu.

`services.server_gateway` est une entrée distincte sur `127.0.0.1:8767` pour
le menu Minecraft. Elle expose uniquement `/health`, `/v1/server/status` et
`/v1/server/start` ; les routes de comptes restent privées sur le port 8766.
Le menu reçoit l'état réel du serveur, pas un pourcentage inventé. La clé API
exaroton et l'ID du serveur restent dans `private/` sur Debian.
Sur la machine actuelle, le port HTTPS 443 de Tailscale Funnel publie déjà un
autre service. Le menu 1.3.0 utilise le port 8443, dirigé vers `127.0.0.1:8767`.
N'activer ce Funnel qu'après avoir configuré `private/exaroton.token` et
`private/exaroton-server.txt` et vérifié le démarrage local du gateway.
- `POST /v1/accounts/register` : JSON `username`, `password`; pseudo ASCII unique sans distinction de casse.
- `POST /v1/accounts/login` : mêmes champs, renvoie une session de sept jours, révoque l'ancienne.
- `GET /v1/accounts/me` : en-tête `Authorization: Bearer <session>`.
- `POST /v1/accounts/logout` : même en-tête, JSON vide.

Mots de passe de 12 à 128 caractères, scrypt N=131072/r=8/p=1 et sel aléatoire par compte.
Jetons de session hachés en SHA-256. Base SQLite et dossier `private` non publics.
Ne jamais les copier sur GitHub. La dernière IP de connexion réussie est conservée
pour les bannissements. Les requêtes et mots de passe ne sont pas journalisés.
Pas de récupération de mot de passe ni de vérification email dans cette première base.

## Configurer exaroton

La clé se crée sur la page Compte exaroton. Sur Debian, créer avec un éditeur :

- `/home/alex/BLIXWOU-Services/private/exaroton.token` : clé API seule.
- `/home/alex/BLIXWOU-Services/private/exaroton-server.txt` : identifiant exaroton du serveur, pas son adresse réseau.

Protéger les deux fichiers par `chmod 600`. Ne pas coller la clé dans une commande
ni dans une conversation. Le service relit ces fichiers après expiration du cache.
Sans configuration ou en cas d'erreur réseau, il répond « Indisponible ».
Il n'expose que l'état et les compteurs, jamais la liste des joueurs ni la clé.
Documentation de référence : https://developers.exaroton.com/

## Modération depuis SSH

```sh
cd /home/alex/BLIXWOU-Services
.venv/bin/python -m services.api --ban-user Pseudo
.venv/bin/python -m services.api --ban-ip 192.0.2.10
.venv/bin/python -m services.api --ban-user Pseudo --unban
```

## Avant l'ouverture aux joueurs

Configurer le domaine, HTTPS et un reverse proxy. Le service n'accepte actuellement
aucun en-tête IP transmis par un proxy : `REMOTE_ADDR` est la seule source d'IP.
Il faudra configurer explicitement le proxy de confiance dans Waitress avant publication,
sinon tous les joueurs auraient l'IP du proxy. Tester ce point et les bans avant ouverture.
Prévoir la sauvegarde privée de la base, l'information sur les IP stockées et une politique
de suppression. Raccorder ensuite le launcher et le serveur de jeu séparément.
L'API exaroton et les inscriptions depuis Internet ne sont pas testables sans leur configuration.
