from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from services.api import Service


class APITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = Service(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def call(self, path, data=None, token='', ip='192.0.2.10', **headers):
        body = json.dumps(data).encode() if data is not None else b''
        env = dict(PATH_INFO=path, REQUEST_METHOD='POST' if data is not None else 'GET',
                   CONTENT_TYPE='application/json', CONTENT_LENGTH=str(len(body)), REMOTE_ADDR=ip,
                   HTTP_AUTHORIZATION='Bearer ' + token, **headers)
        env['wsgi.input'] = io.BytesIO(body)
        statuses = []
        response = b''.join(self.service(env, lambda status, headers: statuses.append(int(status.split()[0]))))
        return statuses[0], json.loads(response)

    def register(self):
        return self.call('/v1/accounts/register', {'username': 'TestPlayer', 'password': 'a-long-test-password'})

    def login(self):
        return self.call('/v1/accounts/login', {'username': 'testplayer', 'password': 'a-long-test-password'})

    def test_account_lifecycle_and_private_storage(self):
        self.assertEqual(self.register()[0], 201)
        status, login = self.login()
        self.assertEqual(status, 200)
        token = login['token']
        self.assertEqual(self.call('/v1/accounts/me', token=token)[1]['username'], 'TestPlayer')
        with closing(self.service.connect()) as db, db:
            user = db.execute('SELECT * FROM users').fetchone()
            self.assertNotEqual(user['password'], b'a-long-test-password')
            self.assertEqual(len(user['salt']), 32)
            self.assertEqual(db.execute('SELECT digest FROM sessions').fetchone()[0], hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(self.call('/v1/accounts/logout', {}, token=token)[0], 200)
        self.assertEqual(self.call('/v1/accounts/me', token=token)[0], 401)

    def test_unique_name_wrong_password_and_ban(self):
        self.register()
        self.assertEqual(self.call('/v1/accounts/register', {'username': 'TESTPLAYER', 'password': 'another-long-password'})[0], 409)
        self.assertEqual(self.call('/v1/accounts/login', {'username': 'TestPlayer', 'password': 'incorrect-password'})[0], 401)
        token = self.login()[1]['token']
        self.service.ban(username='TestPlayer')
        self.assertEqual(self.call('/v1/accounts/me', token=token)[0], 401)
        self.assertEqual(self.login()[0], 401)

    def test_ip_ban_cannot_be_bypassed_with_forwarded_header(self):
        self.service.ban(ip='192.0.2.10')
        status, _ = self.call('/v1/accounts/register', {'username': 'Player2', 'password': 'another-password'},
                              HTTP_X_FORWARDED_FOR='192.0.2.99')
        self.assertEqual(status, 403)
        self.service.ban(ip='192.0.2.10', remove=True)
        self.assertEqual(self.register()[0], 201)

    def test_invalid_input_browser_origin_and_missing_configuration(self):
        self.assertEqual(self.call('/health')[0], 200)
        self.assertFalse(self.call('/v1/server/status')[1]['configured'])
        self.assertEqual(self.call('/v1/accounts/register', {'username': '../oops', 'password': 'short'})[0], 400)
        self.assertEqual(self.call('/v1/accounts/register', {}, HTTP_ORIGIN='https://example.org')[0], 403)

    def test_rate_limit_and_expiry(self):
        self.register()
        token = self.login()[1]['token']
        with closing(self.service.connect()) as db, db:
            db.execute('UPDATE sessions SET expires=0')
            db.execute("UPDATE limits SET count=20 WHERE subject='ip:192.0.2.10'")
        self.assertEqual(self.call('/v1/accounts/me', token=token)[0], 401)
        self.assertEqual(self.login()[0], 429)


if __name__ == '__main__':
    unittest.main()
