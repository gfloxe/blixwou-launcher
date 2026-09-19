import json
from pathlib import Path

import pytest
import requests

from blixwou import firebase_accounts as module
from blixwou.config import LauncherError


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'protect', lambda data, decrypt=False: data[::-1])
    return module.FirebaseAccounts(tmp_path, {'projectId': 'blixwou', 'apiKey': 'test-public-key'})


SESSION = {'localId': 'test-uid', 'idToken': 'test-id-token', 'refreshToken': 'test-refresh-token'}


def test_session_has_no_password_and_logout_preserves_minecraft(accounts):
    minecraft = accounts.path.parent / 'account.dpapi'
    minecraft.write_bytes(b'minecraft-unchanged')
    accounts.save_session(SESSION | {'password': 'not-saved', 'email': 'not-saved@example.org'})
    stored = json.loads(accounts.path.read_bytes()[::-1])
    assert stored == SESSION
    accounts.logout()
    assert not accounts.path.exists()
    assert minecraft.read_bytes() == b'minecraft-unchanged'


def test_registration_uses_atomic_unique_claim(accounts, monkeypatch):
    calls = []
    profiles = iter([None, 'gfloxe'])
    monkeypatch.setattr(accounts, 'profile', lambda: next(profiles))
    monkeypatch.setattr(accounts, 'call', lambda method, url, **kwargs: calls.append((url, kwargs)) or {})
    accounts.save_session(SESSION)
    assert accounts.claim_name('GFLOXE') == 'gfloxe'
    url, payload = calls[0]
    assert url.endswith('/documents:commit')
    writes = payload['json']['writes']
    assert len(writes) == 2
    assert all(w['currentDocument'] == {'exists': False} for w in writes)
    assert writes[0]['update']['fields'] == {'username': {'stringValue': 'gfloxe'}}
    assert writes[1]['update']['name'].endswith('/usernames/gfloxe')
    assert writes[1]['update']['fields'] == {'uid': {'stringValue': 'test-uid'}}


def test_firestore_failure_keeps_auth_session_for_retry(accounts, monkeypatch):
    monkeypatch.setattr(accounts, 'auth', lambda *args: SESSION)
    def fail(*args): raise LauncherError('Firestore indisponible')
    monkeypatch.setattr(accounts, 'claim_name', fail)
    with pytest.raises(LauncherError):
        accounts.register('test@example.org', 'long-test-password', 'TestPlayer')
    assert accounts.path.exists()
    assert accounts.session['localId'] == 'test-uid'


def test_refresh_rotates_saved_tokens(accounts, monkeypatch):
    accounts.save_session(SESSION)
    def call(method, url, **kwargs):
        assert url.startswith('https://securetoken.googleapis.com/')
        assert kwargs['data']['refresh_token'] == SESSION['refreshToken']
        return {'id_token': 'new-id', 'refresh_token': 'new-refresh', 'user_id': 'test-uid'}
    monkeypatch.setattr(accounts, 'call', call)
    monkeypatch.setattr(accounts, 'profile', lambda: 'gfloxe')
    assert accounts.resume() == 'gfloxe'
    assert accounts.session['refreshToken'] == 'new-refresh'


def test_ban_revokes_local_session(accounts, monkeypatch):
    accounts.save_session(SESSION)
    monkeypatch.setattr(accounts, 'call', lambda *args, **kwargs: {'fields': {}})
    with pytest.raises(LauncherError, match='banni'):
        accounts.profile()
    assert accounts.session is None and not accounts.path.exists()


@pytest.mark.parametrize('status,code,expected', [(400,'EMAIL_EXISTS','déjà'), (403,'PERMISSION_DENIED','règles'), (409,'ALREADY_EXISTS','réservé')])
def test_provider_errors_never_show_private_response(accounts, monkeypatch, status, code, expected):
    def fail(*args, **kwargs):
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps({'error': {'message': code}, 'secret': 'PRIVATE-TOKEN'}).encode()
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(module, 'request', fail)
    with pytest.raises(LauncherError, match=expected) as error:
        accounts.call('POST', 'https://example.org')
    assert 'PRIVATE-TOKEN' not in str(error.value)


@pytest.mark.parametrize('name', ['ab', 'with space', '../player', 'a'*17])
def test_invalid_names_rejected(accounts, name):
    with pytest.raises(LauncherError): accounts.name(name)


def test_dialog_controls_no_network(tmp_path):
    from PySide6.QtWidgets import QApplication, QLineEdit
    from blixwou.firebase_ui import FirebaseDialog
    app = QApplication.instance() or QApplication([])
    client = module.FirebaseAccounts(tmp_path, {'projectId': 'blixwou', 'apiKey': 'test'})
    dialog = FirebaseDialog(client, None)
    assert dialog.password.echoMode() == QLineEdit.Password
    assert dialog.auth_panel.isVisibleTo(dialog)
    assert not dialog.claim_panel.isVisibleTo(dialog)
    assert not dialog.profile_panel.isVisibleTo(dialog)
    assert not dialog.logout_button.isVisibleTo(dialog)
    dialog.set_mode('register')
    assert dialog.username_group.isVisibleTo(dialog)
    assert dialog.submit_button.text().startswith('Créer')
    dialog.perform('login')
    assert dialog.job is None and 'e-mail' in dialog.notice.text()
    dialog.close()
