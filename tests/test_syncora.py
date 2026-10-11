import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import base64

from services.api import APIError
from services.pack_publish import PackPublisher
from services.syncora_admin import Syncora, ORIGIN


class SyncoraTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.services = root / 'BLIXWOU-Services'
        private = self.services / 'private'; private.mkdir(parents=True)
        (private / 'syncora-pack-token').write_text('x' * 48)
        (private / 'exaroton-server.txt').write_text('abcdefgh')
        pack = self.services / 'pack'; pack.mkdir()
        (pack / 'manifest.json').write_text(json.dumps({'files': [], 'packVersion': 'initial'}))
        self.app = Syncora(root / 'Syncora', self.services)
        self.publisher = self.app.publisher

    def request(self, path, method='GET', data=None, cookie='', origin=ORIGIN):
        payload = json.dumps(data).encode() if data is not None else b''
        env = dict(PATH_INFO='/syncora/api/' + path, REQUEST_METHOD=method,
                   HTTP_COOKIE=cookie, HTTP_ORIGIN=origin, CONTENT_LENGTH=str(len(payload)))
        env['wsgi.input'] = io.BytesIO(payload)
        response = []
        result = b''.join(self.app(env, lambda status, headers: response.append((status, headers))))
        return response[0], json.loads(result)

    def test_authentication_csrf_logout_and_no_public_registration(self):
        self.app.set_password('admin', 'a long password for the test')
        response, _ = self.request('history')
        self.assertTrue(response[0].startswith('401'))
        response, _ = self.request('login', 'POST', {'name': 'admin', 'password': 'wrong'})
        self.assertTrue(response[0].startswith('401'))
        response, _ = self.request('login', 'POST', {'name': 'admin', 'password': 'a long password for the test'})
        self.assertTrue(response[0].startswith('200'))
        cookie = dict(response[1])['Set-Cookie']
        self.assertIn('HttpOnly; SameSite=Strict', cookie)
        response, _ = self.request('history', cookie=cookie)
        self.assertTrue(response[0].startswith('200'))
        response, _ = self.request('files', 'DELETE', {}, cookie, 'https://evil.example')
        self.assertTrue(response[0].startswith('403'))
        response, _ = self.request('logout', 'POST', {}, cookie)
        self.assertTrue(response[0].startswith('200'))
        response, _ = self.request('history', cookie=cookie)
        self.assertTrue(response[0].startswith('401'))

    def test_publish_preserves_old_objects_and_rejects_paths_and_partial_upload(self):
        self.app.publish('mods/test.jar', b'first', 'both')
        first = self.publisher.snapshot()['files'][0]
        self.assertEqual(first['sha256'], hashlib.sha256(b'first').hexdigest())
        self.app.publish('mods/test.jar', b'second', 'client')
        self.assertEqual(self.publisher.snapshot()['files'][0]['side'], 'both')
        self.assertTrue((self.services / 'pack' / 'objects' / first['sha256']).exists())
        before = self.publisher.snapshot()
        for path in ('../secret.jar', 'mods/../secret.jar', 'mods/CON.jar', 'mods/test.exe'):
            with self.assertRaises(APIError):
                self.app.publish(path, b'bad')
        with self.assertRaises(APIError):
            self.publisher.handle({'REQUEST_METHOD': 'PUT', 'HTTP_AUTHORIZATION': 'Bearer ' + 'x' * 48,
                                   'HTTP_X_PACK_PATH': 'mods/test.jar', 'CONTENT_LENGTH': '100',
                                   'wsgi.input': io.BytesIO(b'truncated')})
        self.assertEqual(self.publisher.snapshot(), before)
        self.assertTrue((self.services / 'pack' / 'primary').exists())
        self.app.publish('mods/test.jar')
        self.assertEqual(self.publisher.snapshot()['files'], [])

    def test_pack_write_requires_token(self):
        with self.assertRaises(APIError) as error:
            self.publisher.handle({'REQUEST_METHOD': 'GET'})
        self.assertEqual(error.exception.status, 401)

    def test_static_cannot_read_private(self):
        result = []
        body = b''.join(self.app({'PATH_INFO': '/syncora/../private/syncora.sqlite3',
                                 'REQUEST_METHOD': 'GET'}, lambda status, headers: result.append(status)))
        self.assertTrue(result[0].startswith('404'))
        self.assertNotIn(b'SQLite format', body)

    def test_backup_publishes_one_commit_without_force_and_only_deletes_tracked_files(self):
        from services.pack_backup import backup
        self.app.publish('mods/test.jar', b'test')
        (self.app.private / 'github.token').write_text('test-token')
        calls = []

        def upstream(app, url, token, method='GET', data=None, accept='application/json'):
            document = json.loads(data) if data else None
            calls.append((url, method, document))
            if '/git/ref/heads/' in url:
                result = {'object': {'sha': 'parent'}}
            elif '/git/commits/parent' in url:
                result = {'tree': {'sha': 'old-tree'}}
            elif '/git/trees/old-tree' in url:
                result = {'tree': [{'path': 'mods/old.jar', 'sha': 'old', 'type': 'blob'},
                                   {'path': 'README.md', 'sha': 'keep', 'type': 'blob'}]}
            elif '/contents/manifest.json' in url:
                result = {'content': base64.b64encode(json.dumps({'files': [{'path': 'mods/old.jar'}]}).encode()).decode()}
            elif '/git/blobs' in url:
                result = {'sha': 'blob-' + str(len(calls))}
            elif '/git/trees' in url:
                result = {'sha': 'new-tree'}
            elif '/git/commits' in url:
                result = {'sha': 'new-commit'}
            else:
                result = {}
            return json.dumps(result).encode()

        with patch.object(Syncora, 'upstream', upstream):
            backup(self.app.root, self.services)
        commits = [doc for url, method, doc in calls if url.endswith('/git/commits')]
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]['parents'], ['parent'])
        self.assertIn('[skip ci]', commits[0]['message'])
        self.assertEqual(calls[-1][2], {'sha': 'new-commit', 'force': False})
        tree = next(doc for url, method, doc in calls if url.endswith('/git/trees'))
        self.assertEqual([e['path'] for e in tree['tree'] if e['sha'] is None], ['mods/old.jar'])
        blobs = [json.loads(base64.b64decode(doc['content'])) for url, method, doc in calls
                 if url.endswith('/git/blobs') and base64.b64decode(doc['content']).startswith(b'{')]
        self.assertTrue(blobs[0]['files'][0]['url'].startswith('https://raw.githubusercontent.com/'))
        self.assertNotIn('fallbackUrl', blobs[0]['files'][0])
        self.assertEqual((self.app.private / 'backup-version.txt').read_text(), self.publisher.snapshot()['packVersion'])
