"""Community accounts via Firebase REST; never used as Minecraft credentials."""
import json
import os
import re
from urllib.parse import quote

import requests

from .auth import protect
from .config import LauncherError
from .network import request


class FirebaseAccounts:
    def __init__(self, root, config):
        self.path = root / 'firebase-account.dpapi'
        self.key = config['apiKey']
        project = config['projectId']
        if not re.fullmatch(r'[a-z][a-z0-9-]{4,29}', project):
            raise LauncherError('Projet Firebase invalide.')
        self.documents = f'projects/{project}/databases/(default)/documents'
        self.base = 'https://firestore.googleapis.com/v1/' + self.documents
        self.session = None
        self.username = None

    def call(self, method, url, *, missing=False, **kwargs):
        try:
            with request(method, url, timeout=10, **kwargs) as response:
                result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except requests.HTTPError as error:
            status = error.response.status_code
            if missing and status == 404:
                return None
            try:
                code = error.response.json().get('error', {}).get('message', '').split(' : ')[0]
            except (ValueError, AttributeError):
                code = ''
            messages = {
                'EMAIL_EXISTS': 'Cet e-mail possède déjà un compte. Connectez-vous.',
                'INVALID_EMAIL': 'Adresse e-mail invalide.',
                'INVALID_LOGIN_CREDENTIALS': 'E-mail ou mot de passe incorrect.',
                'INVALID_PASSWORD': 'E-mail ou mot de passe incorrect.',
                'EMAIL_NOT_FOUND': 'E-mail ou mot de passe incorrect.',
                'USER_DISABLED': 'Ce compte a été désactivé.',
                'OPERATION_NOT_ALLOWED': 'Activez la connexion e-mail/mot de passe dans Firebase Authentication.',
                'CONFIGURATION_NOT_FOUND': 'Firebase Authentication doit encore être configuré.',
                'TOO_MANY_ATTEMPTS_TRY_LATER': 'Trop de tentatives. Réessayez plus tard.',
                'TOKEN_EXPIRED': 'Session expirée. Reconnectez-vous.',
                'INVALID_REFRESH_TOKEN': 'Session expirée. Reconnectez-vous.',
            }
            message = messages.get(code)
            if not message and code.startswith('WEAK_PASSWORD'):
                message = 'Ce mot de passe ne respecte pas la politique Firebase.'
            if not message:
                message = {403: 'Accès refusé : vérifiez les règles Firestore ou le bannissement du compte.',
                           409: 'Ce pseudo est déjà réservé, ou le profil existe déjà.',
                           429: 'Service occupé. Réessayez plus tard.'}.get(status, 'Firebase est indisponible ou mal configuré.')
            raise LauncherError(message) from None
        except (requests.RequestException, ValueError):
            raise LauncherError('Connexion à Firebase impossible. Vérifiez votre accès Internet.') from None

    def auth(self, action, payload):
        return self.call('POST', 'https://identitytoolkit.googleapis.com/v1/accounts:' + action + '?key=' + quote(self.key), json=payload)

    @staticmethod
    def name(value):
        value = value.strip().lower()
        if not re.fullmatch(r'[a-z0-9_]{3,16}', value):
            raise LauncherError('Pseudo : 3 à 16 lettres, chiffres ou _. Les majuscules sont converties en minuscules.')
        return value

    def save_session(self, response):
        session = {key: response[key] for key in ('idToken', 'refreshToken', 'localId')}
        if any(not isinstance(value, str) or not value for value in session.values()):
            raise LauncherError('Réponse de connexion Firebase invalide.')
        self.session = session
        self.username = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = protect(json.dumps(session).encode())
        temp = self.path.with_suffix('.tmp')
        with temp.open('wb') as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)

    def register(self, email, password, username):
        username = self.name(username)
        if not 12 <= len(password) <= 128:
            raise LauncherError('Utilisez un mot de passe de 12 à 128 caractères.')
        response = self.auth('signUp', {'email': email.strip(), 'password': password, 'returnSecureToken': True})
        try:
            self.save_session(response)
            # Keep the Auth account if Firestore is unavailable; retry profile creation after login.
            self.claim_name(username)
        except LauncherError as error:
            raise LauncherError('Compte créé. Le pseudo reste à valider : ' + str(error)
                                + ' Reconnectez-vous si nécessaire, puis utilisez « Valider mon pseudo ».') from None
        return self.username

    def login(self, email, password):
        self.save_session(self.auth('signInWithPassword', {'email': email.strip(), 'password': password, 'returnSecureToken': True}))
        return self.profile()

    def resume(self):
        if not self.path.exists():
            return None
        try:
            saved = json.loads(protect(self.path.read_bytes(), decrypt=True))
            refresh = saved['refreshToken']
        except (ValueError, KeyError, OSError):
            raise LauncherError('Session locale illisible. Reconnectez-vous.') from None
        response = self.call('POST', 'https://securetoken.googleapis.com/v1/token?key=' + quote(self.key),
                             data={'grant_type': 'refresh_token', 'refresh_token': refresh})
        self.save_session({'idToken': response['id_token'], 'refreshToken': response['refresh_token'], 'localId': response['user_id']})
        return self.profile()

    def headers(self):
        if not self.session:
            raise LauncherError('Connectez-vous à votre compte BLIXWOU.')
        return {'Authorization': 'Bearer ' + self.session['idToken']}

    def profile(self):
        uid = quote(self.session['localId'], safe='')
        ban = self.call('GET', self.base + '/bans/' + uid, headers=self.headers(), missing=True)
        if ban is not None:
            self.logout()
            raise LauncherError('Ce compte BLIXWOU est banni.')
        profile = self.call('GET', self.base + '/users/' + uid, headers=self.headers(), missing=True)
        self.username = profile['fields']['username']['stringValue'] if profile else None
        return self.username

    def claim_name(self, username):
        username = self.name(username)
        if self.profile():
            return self.username
        uid = self.session['localId']
        writes = []
        for collection, ident, fields in (
            ('users', uid, {'username': {'stringValue': username}}),
            ('usernames', username, {'uid': {'stringValue': uid}}),
        ):
            writes.append({'update': {'name': self.documents + '/' + collection + '/' + ident, 'fields': fields},
                           'currentDocument': {'exists': False},
                           'updateTransforms': [{'fieldPath': 'createdAt', 'setToServerValue': 'REQUEST_TIME'}]})
        self.call('POST', self.base + ':commit', headers=self.headers(), json={'writes': writes})
        return self.profile()

    def reset_password(self, email):
        try:
            self.auth('sendOobCode', {'requestType': 'PASSWORD_RESET', 'email': email.strip()})
        except LauncherError as error:
            if str(error) != 'E-mail ou mot de passe incorrect.':
                raise
        return 'Si ce compte existe, un e-mail de réinitialisation a été envoyé.'

    def logout(self):
        self.session, self.username = None, None
        self.path.unlink(missing_ok=True)
