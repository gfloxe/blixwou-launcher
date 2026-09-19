"""Run interactively over SSH. Never put the API key in shell history."""
import getpass
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


def main():
    if not __import__('sys').stdin.isatty():
        raise SystemExit('Lancez cette commande dans votre session SSH interactive.')
    token = getpass.getpass('Clé API exaroton (saisie masquée) : ').strip()
    if not token:
        raise SystemExit('Aucune clé saisie.')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    request = urllib.request.Request('https://api.exaroton.com/v1/servers/', headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            document = json.load(response)
        servers = [s for s in document.get('data', []) if s.get('address', '').lower() == 'blixwou.exaroton.me']
        if not document.get('success') or len(servers) != 1:
            raise SystemExit('Serveur BLIXWOU introuvable ou ambigu. Aucun fichier modifié.')
    except urllib.error.HTTPError as error:
        raise SystemExit(f'exaroton refuse la requête (HTTP {error.code}). Aucun fichier modifié.') from None
    except (OSError, ValueError):
        raise SystemExit('Connexion à exaroton impossible. Aucun fichier modifié.') from None
    os.umask(0o077)
    folder = Path.home() / 'BLIXWOU-Services' / 'private'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, value in [('exaroton.token', token), ('exaroton-server.txt', servers[0]['id'])]:
        temporary = folder / (name + '.tmp')
        temporary.write_text(value + '\n')
        temporary.chmod(0o600)
        temporary.replace(folder / name)
    print('Clé vérifiée et enregistrée. Statut disponible dans quelques secondes.')


if __name__ == '__main__':
    main()
