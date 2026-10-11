"""Syncora Debian: protected administration, static UI and pack publishing.

No public registration. Provision/reset the sole administrator through SSH.
All paths and upstream hosts are server controlled; credentials stay private.
"""
from contextlib import closing
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.cookies import SimpleCookie
import hashlib
import hmac
import io
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

from .api import APIError
from .pack_publish import PackPublisher, archive_path, MAX_SIZE

ORIGIN = 'https://debian-machine.tail7d0337.ts.net:8443'
PREFIX = '/syncora'


def derive(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1,
                          maxmem=64 * 1024 * 1024)


class Syncora:
    def __init__(self, root, services):
        self.root, self.services = Path(root), Path(services)
        self.private = self.root / 'private'
        self.private.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.private / 'syncora.sqlite3'
        self.publisher = PackPublisher(self.services / 'private', self.services / 'pack')
        with closing(self.connect()) as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS admin (name TEXT PRIMARY KEY, salt BLOB, hash BLOB);
              CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, expires INTEGER);
              CREATE TABLE IF NOT EXISTS attempts (started INTEGER);
              CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, document TEXT);
            ''')
        if os.name != 'nt':
            self.database.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.database, timeout=30)

    def set_password(self, name, password):
        if not name.strip() or len(name) > 64 or len(password) < 14:
            raise ValueError('Identifiant requis et mot de passe de 14 caractères minimum.')
        salt = secrets.token_bytes(32)
        digest = derive(password, salt)
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM admin')
            db.execute('INSERT INTO admin VALUES (?,?,?)', (name, salt, digest))
            db.execute('DELETE FROM sessions')

    def authenticated(self, env):
        cookie = SimpleCookie()
        try:
            cookie.load(env.get('HTTP_COOKIE', ''))
            token = cookie['syncora_session'].value
        except (KeyError, ValueError):
            return False
        with closing(self.connect()) as db:
            return bool(db.execute('SELECT 1 FROM sessions WHERE digest=? AND expires>?',
                                   (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone())

    def body(self, env, maximum=16384):
        try:
            length = int(env.get('CONTENT_LENGTH') or 0)
        except ValueError:
            raise APIError(400, 'Taille invalide.') from None
        if length < 0 or length > maximum:
            raise APIError(413, 'Envoi trop volumineux.')
        data = env['wsgi.input'].read(length)
        if len(data) != length:
            raise APIError(400, 'Envoi incomplet.')
        return data

    def json_body(self, env):
        try:
            body = json.loads(self.body(env))
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except (ValueError, UnicodeError):
            raise APIError(400, 'Requête invalide.') from None

    def login(self, env):
        body = self.json_body(env)
        now = int(time.time())
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM attempts WHERE started<?', (now - 600,))
            if db.execute('SELECT count(*) FROM attempts').fetchone()[0] >= 10:
                raise APIError(429, 'Trop de tentatives. Attendez 10 minutes.')
            db.execute('INSERT INTO attempts VALUES (?)', (now,))
        with closing(self.connect()) as db, db:
            row = db.execute('SELECT name,salt,hash FROM admin').fetchone()
            password = body.get('password', '')
            if not isinstance(password, str) or len(password) > 512:
                raise APIError(401, 'Identifiants incorrects.')
            candidate = derive(password, row[1] if row else bytes(32))
            if not row or body.get('name') != row[0] or not hmac.compare_digest(candidate, row[2]):
                raise APIError(401, 'Identifiants incorrects.')
            token = secrets.token_urlsafe(48)
            db.execute('DELETE FROM sessions WHERE expires<?', (now,))
            db.execute('INSERT INTO sessions VALUES (?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), now + 8 * 3600))
        return token

    def credential(self, name):
        folder = self.private if name == 'github.token' else self.services / 'private'
        try:
            return (folder / name).read_text().strip()
        except OSError:
            return ''

    def upstream(self, url, token, method='GET', data=None, accept='application/json'):
        # Never follow an authenticated redirect to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        headers = {'Authorization': 'Bearer ' + token, 'User-Agent': 'Syncora-Debian',
                   'Accept': accept}
        if data is not None:
            headers['Content-Type'] = 'application/json' if 'api.github.com' in url else 'application/octet-stream'
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
                payload = response.read(MAX_SIZE + 1)
                if len(payload) > MAX_SIZE:
                    raise APIError(413, 'Fichier distant trop volumineux.')
                return payload
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise APIError(404, 'Fichier distant introuvable.') from None
            raise APIError(502, f'Service distant refusé ({error.code}).') from None
        except (OSError, urllib.error.URLError):
            raise APIError(502, 'Service distant inaccessible.') from None

    def server_id(self):
        value = self.credential('exaroton-server.txt')
        if not value or not value.isalnum():
            raise APIError(503, 'Serveur exaroton non configuré.')
        return value

    def exaroton(self, kind, path='', method='GET', data=None):
        token = self.credential('exaroton.token')
        if not token:
            raise APIError(503, 'exaroton non configuré.')
        return self.upstream('https://api.exaroton.com/v1/servers/' + self.server_id() +
                             '/files/' + kind + '/' + urllib.parse.quote(path, safe='/') + '/',
                             token, method, data)

    def publish(self, path, data=None, side='client'):
        env = {'REQUEST_METHOD': 'DELETE' if data is None else 'PUT',
               'HTTP_AUTHORIZATION': 'Bearer ' + self.credential('syncora-pack-token'),
               'HTTP_X_PACK_PATH': path, 'HTTP_X_PACK_SIDE': side,
               'CONTENT_LENGTH': str(len(data or b'')), 'wsgi.input': io.BytesIO(data or b'')}
        self.publisher.handle(env)

    def record(self, name, size, debian, server):
        event = dict(fileName=name, baseName=name.rsplit('.', 1)[0], version='synchronisé',
                     size=size, github=debian, server=server, status='ok',
                     createdAt=datetime.now(timezone.utc).isoformat())
        with closing(self.connect()) as db, db:
            event['id'] = db.execute('INSERT INTO history(document) VALUES (?)', (json.dumps(event),)).lastrowid
        return event

    def api(self, env, route):
        method = env['REQUEST_METHOD']
        query = dict(urllib.parse.parse_qsl(env.get('QUERY_STRING', '')))
        if route == 'connections' and method == 'GET':
            return {'configured': {'github': True, 'exaroton': bool(self.credential('exaroton.token'))},
                    'githubReadOnly': False, 'backupConfigured': bool(self.credential('github.token')),
                    'servers': [{'id': self.server_id(), 'name': 'BLIXWOU'}]}
        if route == 'backup' and method == 'GET':
            version = self.publisher.snapshot()['packVersion']
            state = self.private / 'backup-version.txt'
            saved = state.read_text() if state.exists() else None
            return {'configured': bool(self.credential('github.token')),
                    'current': saved == version, 'version': version}
        if route == 'history':
            with closing(self.connect()) as db, db:
                if method == 'DELETE':
                    try:
                        identity = int(query.get('id', ''))
                    except ValueError:
                        raise APIError(400, 'Identifiant invalide.') from None
                    db.execute('DELETE FROM history WHERE id=?', (identity,))
                    return {'deleted': identity}
                if method == 'GET':
                    events = []
                    for identity, document in db.execute('SELECT id,document FROM history ORDER BY id DESC LIMIT 100'):
                        event = json.loads(document); event['id'] = identity; events.append(event)
                    return {'events': events}
        if route == 'snapshot' and method == 'GET':
            directory = query.get('githubPath', 'mods')
            archive_path(directory + ('/check.jar' if directory == 'mods' else '/check.zip'))
            local = {f['path'].split('/')[1]: f['size'] for f in self.publisher.snapshot()['files']
                     if f['path'].startswith(directory + '/') and f['path'].count('/') == 1}
            server_directory = query.get('serverPath', 'mods')
            archive_path(server_directory + ('/check.jar' if server_directory == 'mods' else '/check.zip'))
            payload = json.loads(self.exaroton('info', server_directory))
            if not payload.get('success'):
                raise APIError(502, 'Analyse exaroton impossible.')
            remote = {f.get('name') or f.get('path', '').rsplit('/', 1)[-1]: f.get('size', 0)
                      for f in payload.get('data', {}).get('children', []) if not f.get('isDirectory')}
            files = []
            for name in sorted(local.keys() | remote.keys()):
                if not name.lower().endswith(('.jar', '.zip')):
                    continue
                status = 'server_only' if name not in local else 'github_only' if name not in remote else \
                         'synced' if local[name] == remote[name] else 'different'
                files.append(dict(name=name, githubSize=local.get(name), serverSize=remote.get(name), status=status))
            return {'files': files, 'summary': {'synced': sum(f['status'] == 'synced' for f in files),
                                               'pending': sum(f['status'] != 'synced' for f in files)}}
        if route == 'sync' and method == 'POST':
            raw = self.body(env, MAX_SIZE + 65536)
            content_type = env.get('CONTENT_TYPE', '')
            if not content_type.startswith('multipart/form-data;') or '\r' in content_type or '\n' in content_type:
                raise APIError(400, 'Formulaire requis.')
            message = BytesParser(policy=default).parsebytes(
                ('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + raw)
            values = {}; data = None; name = None
            for part in message.iter_parts():
                field = part.get_param('name', header='content-disposition')
                if field == 'file':
                    data, name = part.get_payload(decode=True), part.get_filename()
                elif field:
                    values[field] = (part.get_payload(decode=True) or b'').decode('utf-8')
            if not name or not data or len(data) > MAX_SIZE:
                raise APIError(400, 'Fichier absent ou invalide.')
            path = archive_path(values.get('githubPath', 'mods') + '/' + name)
            debian, server = values.get('github') == 'true', values.get('server') == 'true'
            if not debian and not server:
                raise APIError(400, 'Choisissez une destination.')
            if server:
                server_path = archive_path(values.get('serverPath', 'mods') + '/' + name)
                if name.startswith('blixwou-menu'):
                    raise APIError(400, 'Le mod menu est réservé au client, pas à exaroton.')
            if debian:
                self.publish(path, data, 'both' if server and path.startswith('mods/') else 'client')
            if server:
                try:
                    self.exaroton('data', server_path, 'PUT', data)
                except APIError as error:
                    if debian:
                        raise APIError(error.status, 'Publié sur Debian, mais exaroton a échoué : ' + error.message) from None
                    raise
            return {'event': self.record(name, len(data), debian, server)}
        if route in ('files', 'reconcile') and method == ('DELETE' if route == 'files' else 'POST'):
            body = self.json_body(env)
            name = body.get('name', '')
            path = archive_path(body.get('githubPath', 'mods') + '/' + name)
            server_path = archive_path(body.get('serverPath', 'mods') + '/' + name)
            if route == 'files':
                if body.get('github'):
                    self.publish(path)
                if body.get('server'):
                    self.exaroton('data', server_path, 'DELETE')
                return {'deleted': name}
            if body.get('source') == 'github':
                if name.startswith('blixwou-menu'):
                    raise APIError(400, 'Le mod menu ne doit pas aller sur exaroton.')
                item = next((f for f in self.publisher.snapshot()['files'] if f['path'] == path), None)
                if not item:
                    raise APIError(404, 'Fichier absent sur Debian.')
                data = (self.services / 'pack' / 'objects' / item['sha256']).read_bytes()
                self.exaroton('data', server_path, 'PUT', data)
            elif body.get('source') == 'server':
                data = self.exaroton('data', server_path)
                self.publish(path, data, 'both' if path.startswith('mods/') else 'client')
            else:
                raise APIError(400, 'Source invalide.')
            return {'event': self.record(name, len(data), True, True), 'synced': True}
        raise APIError(404, 'Route introuvable.')

    def __call__(self, env, start):
        path, method = env.get('PATH_INFO', ''), env.get('REQUEST_METHOD', '')
        headers = [('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                   ('X-Frame-Options', 'DENY'), ('Referrer-Policy', 'no-referrer')]
        try:
            if method not in ('GET', 'HEAD') and env.get('HTTP_ORIGIN') != ORIGIN:
                raise APIError(403, 'Origine refusée.')
            if path == PREFIX + '/api/login' and method == 'POST':
                token = self.login(env)
                headers.append(('Set-Cookie', 'syncora_session=' + token +
                                '; Path=/syncora; Secure; HttpOnly; SameSite=Strict; Max-Age=28800'))
                result = {'ok': True}
            elif path == PREFIX + '/api/session' and method == 'GET':
                result = {'authenticated': self.authenticated(env)}
            elif path == PREFIX + '/api/logout' and method == 'POST':
                cookie = SimpleCookie(); cookie.load(env.get('HTTP_COOKIE', ''))
                if 'syncora_session' in cookie:
                    with closing(self.connect()) as db, db:
                        db.execute('DELETE FROM sessions WHERE digest=?',
                                   (hashlib.sha256(cookie['syncora_session'].value.encode()).hexdigest(),))
                headers.append(('Set-Cookie', 'syncora_session=; Path=/syncora; Secure; HttpOnly; SameSite=Strict; Max-Age=0'))
                result = {'ok': True}
            elif path.startswith(PREFIX + '/api/'):
                if not self.authenticated(env):
                    raise APIError(401, 'Connexion administrateur requise.')
                result = self.api(env, path[len(PREFIX + '/api/'):])
            elif method in ('GET', 'HEAD'):
                relative = path[len(PREFIX):].lstrip('/') or 'index.html'
                target = (self.root / 'web' / relative).resolve()
                if not target.is_relative_to((self.root / 'web').resolve()) or not target.is_file():
                    raise APIError(404, 'Fichier introuvable.')
                payload = target.read_bytes()
                headers.extend([('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream'),
                                ('Content-Length', str(len(payload))),
                                ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")])
                start('200 OK', headers)
                return [b'' if method == 'HEAD' else payload]
            else:
                raise APIError(405, 'Méthode refusée.')
            code = 200
        except APIError as error:
            code, result = error.status, {'error': error.message}
        except Exception:
            code, result = 503, {'error': 'Opération impossible. Consultez le journal Debian.'}
        payload = json.dumps(result, ensure_ascii=False).encode()
        start(f'{code} {HTTPStatus(code).phrase}', headers +
              [('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(payload)))])
        return [payload]


def main():
    import getpass
    os.umask(0o077)
    app = Syncora(Path.home() / 'Syncora', Path.home() / 'BLIXWOU-Services')
    name = input('Identifiant administrateur [admin] : ').strip() or 'admin'
    password = getpass.getpass('Mot de passe (14 caractères minimum) : ')
    if password != getpass.getpass('Confirme le mot de passe : '):
        raise SystemExit('Les mots de passe sont différents.')
    app.set_password(name, password)
    print('Administrateur configuré. Les anciennes sessions sont révoquées.')


if __name__ == '__main__':
    main()
