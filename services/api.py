"""BLIXWOU accounts and coordinated exaroton startup. Listen on loopback only."""
import argparse
from contextlib import closing
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import urllib.request
import uuid


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=131072, r=8, p=1,
                          maxmem=256 * 1024 * 1024, dklen=32)


class Service:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.folder / 'accounts.sqlite3'
        self.auth_lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.start_lock = threading.Lock()
        self.last_start = 0.0
        self.status_time = 0
        self.status_cache = {'state': 'unknown', 'text': 'Indisponible', 'configured': False}
        self.dummy_salt = secrets.token_bytes(32)
        with closing(self.connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                  salt BLOB NOT NULL, password BLOB NOT NULL, created INTEGER NOT NULL,
                  last_ip TEXT NOT NULL, banned INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sessions (
                  digest TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS banned_ips (ip TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS limits (
                  subject TEXT PRIMARY KEY, started INTEGER NOT NULL, count INTEGER NOT NULL);
            ''')
        if os.name != 'nt':
            self.database.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def rate_limit(self, db, subject, maximum):
        now = int(time.time())
        db.execute('DELETE FROM limits WHERE started < ?', (now - 600,))
        row = db.execute('SELECT * FROM limits WHERE subject=?', (subject,)).fetchone()
        if row and row['count'] >= maximum:
            raise APIError(429, 'Trop de tentatives. Réessayez dans quelques minutes.')
        db.execute('INSERT INTO limits VALUES(?,?,1) ON CONFLICT(subject) DO UPDATE SET count=count+1',
                   (subject, now))
        db.commit()  # Failed authentication attempts must also be counted.

    def status(self):
        with self.status_lock:
            if time.monotonic() - self.status_time < 5:
                return self.status_cache
            result = {'state': 'unknown', 'text': 'Indisponible', 'configured': False}
            try:
                token = (self.folder / 'exaroton.token').read_text().strip()
                server = (self.folder / 'exaroton-server.txt').read_text().strip()
                if not token or not re.fullmatch(r'[A-Za-z0-9]{8,64}', server):
                    raise ValueError('configuration')
                result['configured'] = True
                req = urllib.request.Request('https://api.exaroton.com/v1/servers/' + server + '/',
                                             headers={'Authorization': 'Bearer ' + token,
                                                      'User-Agent': 'BLIXWOU-Services/1.0'})
                # No redirects with a secret Authorization header.
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, *args, **kwargs):
                        return None
                with urllib.request.build_opener(NoRedirect()).open(req, timeout=5) as response:
                    body = response.read(262145)
                if len(body) > 262144:
                    raise ValueError('size')
                document = json.loads(body)
                if not document.get('success'):
                    raise ValueError('upstream')
                data = document['data']
                code = data['status']
                labels = {0: 'Hors ligne', 1: 'En ligne', 2: 'Démarrage', 3: 'Arrêt',
                          4: 'Redémarrage', 5: 'Sauvegarde', 6: 'Chargement', 7: 'Arrêt inattendu',
                          8: 'En attente', 9: 'Transfert', 10: 'Préparation'}
                result.update(state='online' if code == 1 else 'offline' if code in (0, 7) else
                              'starting' if code in (2, 4, 6, 8, 9, 10) else 'stopping' if code in (3, 5) else 'unknown',
                              text=labels.get(code, 'Indisponible'), updated_at=int(time.time()))
                players = data.get('players', {})
                if code == 1 and all(type(players.get(k)) is int for k in ('count', 'max')):
                    result.update(online=players['count'], max=players['max'])
                address, port = data.get('address'), data.get('port')
                if code == 1 and isinstance(address, str) and re.fullmatch(r'[A-Za-z0-9.-]+', address) \
                        and type(port) is int and 1 <= port <= 65535:
                    result.update(address=address, port=port)
            except Exception:
                pass  # Never log upstream exceptions containing credentials or player data.
            self.status_cache, self.status_time = result, time.monotonic()
            return result

    def start_server(self):
        """One exaroton start request per transition, shared by all waiting players."""
        with self.start_lock:
            current = self.status()
            if not current['configured'] or current['state'] == 'unknown' and current['text'] == 'Indisponible':
                raise APIError(503, 'État exaroton indisponible. Réessayez plus tard.')
            if current['state'] != 'offline':
                return current
            now = time.monotonic()
            if now - self.last_start < 60:
                return {'state': 'starting', 'text': 'Démarrage demandé', 'configured': True}
            token = (self.folder / 'exaroton.token').read_text().strip()
            server = (self.folder / 'exaroton-server.txt').read_text().strip()
            if not token or not re.fullmatch(r'[A-Za-z0-9]{8,64}', server):
                raise APIError(503, 'Démarrage du serveur indisponible.')
            # exaroton documents GET /start/ as its start action. The key never
            # leaves this Debian service and redirects are refused.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            req = urllib.request.Request('https://api.exaroton.com/v1/servers/' + server + '/start/',
                                         headers={'Authorization': 'Bearer ' + token,
                                                  'User-Agent': 'BLIXWOU-Services/1.0'})
            self.last_start = now
            try:
                with urllib.request.build_opener(NoRedirect()).open(req, timeout=8) as response:
                    body = response.read(65537)
                if len(body) > 65536 or not json.loads(body).get('success'):
                    raise ValueError('upstream')
            except Exception:
                # A timed-out request might still have reached exaroton. Keep
                # the cooldown so another player cannot trigger a duplicate.
                raise APIError(502, 'exaroton n’a pas confirmé le démarrage. Réessayez dans une minute.') from None
            with self.status_lock:
                self.status_cache = {'state': 'starting', 'text': 'Démarrage demandé', 'configured': True}
                self.status_time = time.monotonic()
            return self.status_cache

    def authenticate(self, db, header, ip):
        if db.execute('SELECT 1 FROM banned_ips WHERE ip=?', (ip,)).fetchone():
            raise APIError(403, 'Accès refusé.')
        if not header.startswith('Bearer ') or not re.fullmatch(r'[A-Za-z0-9_-]{43}', header[7:]):
            raise APIError(401, 'Connexion requise.')
        digest = hashlib.sha256(header[7:].encode()).hexdigest()
        user = db.execute('SELECT users.* FROM users JOIN sessions ON users.id=sessions.user_id '
                          'WHERE sessions.digest=? AND sessions.expires>? AND users.banned=0',
                          (digest, int(time.time()))).fetchone()
        if not user:
            raise APIError(401, 'Session expirée ou révoquée.')
        return user, digest

    def route(self, env):
        path, method = env.get('PATH_INFO', ''), env.get('REQUEST_METHOD', '')
        if (method, path) == ('GET', '/health'):
            return 200, {'service': 'BLIXWOU', 'ok': True}
        if (method, path) == ('GET', '/v1/server/status'):
            return 200, self.status()
        if (method, path) == ('POST', '/v1/server/start'):
            if env.get('HTTP_ORIGIN') or env.get('CONTENT_LENGTH') not in (None, '', '0'):
                raise APIError(400, 'Requête invalide.')
            return 202, self.start_server()
        if path not in ('/v1/accounts/register', '/v1/accounts/login', '/v1/accounts/me', '/v1/accounts/logout'):
            raise APIError(404, 'Route introuvable.')
        if method != ('GET' if path.endswith('/me') else 'POST'):
            raise APIError(405, 'Méthode refusée.')
        # No cookies, no CORS. Browser forms must not submit credentials here.
        if env.get('HTTP_ORIGIN'):
            raise APIError(403, 'Utilisez le launcher BLIXWOU.')
        ip = str(ipaddress.ip_address(env.get('REMOTE_ADDR', '127.0.0.1')))
        if path.endswith(('/register', '/login')):
            if env.get('CONTENT_TYPE', '').split(';')[0] != 'application/json':
                raise APIError(415, 'JSON requis.')
            try:
                length = int(env.get('CONTENT_LENGTH') or 0)
                if not 1 <= length <= 4096:
                    raise ValueError()
                body = json.loads(env['wsgi.input'].read(length))
                name, password = body['username'], body['password']
                if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,16}', name):
                    raise ValueError()
                if not isinstance(password, str) or not 12 <= len(password) <= 128:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise APIError(400, 'Pseudo : 3–16 lettres, chiffres ou _. Mot de passe : 12–128 caractères.')
            # Serialize expensive scrypt operations to bound memory consumption.
            with self.auth_lock, closing(self.connect()) as db, db:
                self.rate_limit(db, 'ip:' + ip, 20)
                self.rate_limit(db, 'name:' + name.lower(), 10)
                if db.execute('SELECT 1 FROM banned_ips WHERE ip=?', (ip,)).fetchone():
                    raise APIError(403, 'Accès refusé.')
                db.execute('DELETE FROM sessions WHERE expires<=?', (int(time.time()),))
                if path.endswith('/register'):
                    salt = secrets.token_bytes(32)
                    hashed = password_hash(password, salt)
                    try:
                        db.execute('INSERT INTO users(id,name,salt,password,created,last_ip) VALUES(?,?,?,?,?,?)',
                                   (uuid.uuid4().hex, name, salt, hashed, int(time.time()), ip))
                    except sqlite3.IntegrityError:
                        raise APIError(409, 'Ce pseudo est déjà utilisé.')
                    return 201, {'username': name}
                user = db.execute('SELECT * FROM users WHERE name=?', (name,)).fetchone()
                hashed = password_hash(password, user['salt'] if user else self.dummy_salt)
                if not user or not hmac.compare_digest(hashed, user['password']) or user['banned']:
                    raise APIError(401, 'Identifiants incorrects ou compte indisponible.')
                token = secrets.token_urlsafe(32)
                expires = int(time.time()) + 7 * 86400
                # One active session per account, old sessions revoked on login.
                db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
                db.execute('INSERT INTO sessions VALUES(?,?,?)',
                           (hashlib.sha256(token.encode()).hexdigest(), user['id'], expires))
                db.execute('UPDATE users SET last_ip=? WHERE id=?', (ip, user['id']))
                return 200, {'token': token, 'expires_at': expires, 'username': user['name'], 'id': user['id']}
        with closing(self.connect()) as db, db:
            user, digest = self.authenticate(db, env.get('HTTP_AUTHORIZATION', ''), ip)
            if path.endswith('/logout'):
                db.execute('DELETE FROM sessions WHERE digest=?', (digest,))
                return 200, {'ok': True}
            return 200, {'id': user['id'], 'username': user['name']}

    def __call__(self, env, start_response):
        try:
            status, result = self.route(env)
        except APIError as error:
            status, result = error.status, {'error': error.message}
        except Exception:
            status, result = 503, {'error': 'Service temporairement indisponible.'}
        from http import HTTPStatus
        payload = json.dumps(result, ensure_ascii=False).encode('utf-8')
        start_response(f'{status} {HTTPStatus(status).phrase}', [
            ('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(payload))),
            ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')])
        return [payload]

    def ban(self, *, username=None, ip=None, remove=False):
        with closing(self.connect()) as db, db:
            if ip:
                ip = str(ipaddress.ip_address(ip))
                if remove:
                    db.execute('DELETE FROM banned_ips WHERE ip=?', (ip,))
                else:
                    db.execute('INSERT OR IGNORE INTO banned_ips VALUES(?)', (ip,))
            if username:
                db.execute('UPDATE users SET banned=? WHERE name=?', (int(not remove), username))
                if not remove:
                    db.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE name=?)', (username,))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path.home() / 'BLIXWOU-Services' / 'private')
    parser.add_argument('--ban-user')
    parser.add_argument('--ban-ip')
    parser.add_argument('--unban', action='store_true')
    args = parser.parse_args()
    service = Service(args.data)
    if args.ban_user or args.ban_ip:
        service.ban(username=args.ban_user, ip=args.ban_ip, remove=args.unban)
        print('Règle appliquée aux comptes BLIXWOU.')
        return
    from waitress import serve
    serve(service, listen='127.0.0.1:8766', threads=4, connection_limit=50,
          max_request_body_size=4096, max_request_header_size=8192, channel_timeout=15)


if __name__ == '__main__':
    main()
