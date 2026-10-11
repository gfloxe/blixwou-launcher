"""Authenticated Syncora writes; Debian owns the published pack inventory."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
import time
import uuid
from urllib.parse import quote

from .api import APIError
from .pack_mirror import PUBLIC

MAX_SIZE = 50 * 1024 * 1024
_lock = threading.RLock()


@contextmanager
def pack_lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    with _lock, (folder / '.publish.lock').open('a+b') as stream:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'posix':
                fcntl.flock(stream, fcntl.LOCK_UN)


def archive_path(path):
    if (not isinstance(path, str) or len(path) > 240 or '\\' in path
            or ':' in path or any(ord(c) < 32 or c in '<>"|?*' for c in path)):
        raise APIError(400, 'Chemin de fichier invalide.')
    parts = path.split('/')
    if (len(parts) != 2 or parts[0] not in ('mods', 'shaderpacks', 'resourcepacks')
            or parts[1] in ('', '.', '..') or parts[1].endswith(('.', ' '))
            or re.match(r'^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)', parts[1], re.I)
            or PurePosixPath(path).suffix.lower() != ('.jar' if parts[0] == 'mods' else '.zip')):
        raise APIError(400, 'Choisissez un .jar dans mods ou un .zip dans shaderpacks/resourcepacks.')
    return path


class PackPublisher:
    def __init__(self, private, folder):
        self.private, self.folder = Path(private), Path(folder)

    def authorize(self, env):
        try:
            token = (self.private / 'syncora-pack-token').read_text().strip()
        except OSError:
            raise APIError(503, 'Envoi Syncora non configuré.') from None
        supplied = env.get('HTTP_AUTHORIZATION', '')
        if len(token) < 32 or not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
            raise APIError(401, 'Accès Syncora refusé.')

    def snapshot(self):
        try:
            return json.loads((self.folder / 'manifest.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise APIError(503, 'Pack initial non disponible.') from None

    def save(self, manifest):
        manifest['packVersion'] = f'debian-{time.time_ns()}'
        temporary = self.folder / ('manifest-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
            # Stops the legacy GitHub poller from overwriting Syncora publications.
            (self.folder / 'primary').touch()
            os.replace(temporary, self.folder / 'manifest.json')
        finally:
            temporary.unlink(missing_ok=True)

    def handle(self, env):
        self.authorize(env)
        method = env.get('REQUEST_METHOD')
        if method == 'GET':
            return self.snapshot()
        if method not in ('PUT', 'DELETE'):
            raise APIError(405, 'Méthode refusée.')
        path = archive_path(env.get('HTTP_X_PACK_PATH', ''))
        with pack_lock(self.folder):
            manifest = self.snapshot()
            previous = next((f for f in manifest['files'] if f['path'].casefold() == path.casefold()), None)
            if method == 'DELETE':
                if not previous:
                    raise APIError(404, 'Fichier absent du pack.')
                manifest['files'].remove(previous)
                self.save(manifest)
                return manifest
            try:
                size = int(env.get('CONTENT_LENGTH', ''))
            except (ValueError, TypeError):
                raise APIError(411, 'Taille requise.') from None
            if not 0 < size <= MAX_SIZE:
                raise APIError(413, 'La limite est de 50 Mo.')
            side = previous['side'] if previous else env.get('HTTP_X_PACK_SIDE', 'client')
            if side not in ('client', 'both', 'server'):
                raise APIError(400, 'Côté du mod invalide.')
            objects = self.folder / 'objects'
            objects.mkdir(exist_ok=True)
            temporary = objects / (uuid.uuid4().hex + '.upload')
            digest = hashlib.sha256()
            try:
                with temporary.open('wb') as output:
                    remaining = size
                    while remaining:
                        chunk = env['wsgi.input'].read(min(remaining, 256 * 1024))
                        if not chunk:
                            raise APIError(400, 'Envoi incomplet.')
                        remaining -= len(chunk)
                        digest.update(chunk)
                        output.write(chunk)
                sha = digest.hexdigest()
                os.replace(temporary, objects / sha)
            finally:
                temporary.unlink(missing_ok=True)
            entry = {'path': previous['path'] if previous else path, 'size': size, 'sha256': sha,
                     'side': side, 'policy': previous['policy'] if previous else 'enforced',
                     'url': PUBLIC + '/pack/objects/' + sha,
                     'fallbackUrl': 'https://raw.githubusercontent.com/gfloxe/BLIXWOU/main/' +
                                    quote(path, safe='/')}
            manifest['files'] = [f for f in manifest['files'] if f['path'].casefold() != path.casefold()] + [entry]
            self.save(manifest)
            return manifest
