import json
import io
import pytest
import requests
from blixwou.config import LauncherError
from blixwou.pack import PackManager
from tests.test_pack import manifest, item
from services.server_gateway import ServerGateway
from services import pack_mirror


def test_primary_manifest_and_fallback(tmp_path, monkeypatch):
    calls = []
    def get(url):
        calls.append(url)
        if url == 'https://primary.invalid/manifest':
            raise requests.ConnectionError('offline')
        return manifest()
    monkeypatch.setattr('blixwou.pack.get_json', get)
    result = PackManager(tmp_path).fetch_manifest('https://primary.invalid/manifest', fallback_url='https://backup.invalid/manifest')
    assert result['packVersion'] == '1'
    assert calls == ['https://primary.invalid/manifest', 'https://backup.invalid/manifest']


def test_invalid_primary_uses_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr('blixwou.pack.get_json', lambda url: {} if 'primary' in url else manifest())
    assert PackManager(tmp_path).fetch_manifest('https://primary.invalid/', fallback_url='https://backup.invalid/')['packVersion'] == '1'


def test_file_fallback_keeps_digest(tmp_path, monkeypatch):
    entry = item('mods/test.jar')
    entry['fallbackUrl'] = 'https://backup.invalid/test.jar'
    calls = []
    def download(url, target, sha, size, progress):
        calls.append((url, sha, size))
        if url == entry['url']:
            raise LauncherError('offline')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'data')
    monkeypatch.setattr('blixwou.pack.download', download)
    PackManager(tmp_path).sync(manifest([entry]))
    assert (tmp_path / 'game/mods/test.jar').read_bytes() == b'data'
    assert calls == [(entry['url'], entry['sha256'], 4), (entry['fallbackUrl'], entry['sha256'], 4)]


def test_gateway_only_serves_public_objects(tmp_path, monkeypatch):
    monkeypatch.setattr('services.server_gateway.Service', lambda folder: None)
    gateway = ServerGateway(tmp_path / 'private')
    folder = tmp_path / 'pack'
    folder.mkdir()
    (folder / 'manifest.json').write_text('{}')
    statuses = []
    def start(status, headers):
        statuses.append(status)
    assert b''.join(gateway({'REQUEST_METHOD': 'GET', 'PATH_INFO': '/pack/manifest.json'}, start)) == b'{}'
    assert statuses[-1] == '200 OK'
    gateway({'REQUEST_METHOD': 'GET', 'PATH_INFO': '/pack/../private/config.json'}, start)
    assert statuses[-1] == '404 Not Found'


def test_mirror_publishes_only_complete_verified_snapshot(tmp_path, monkeypatch):
    entry = item('mods/test.jar')
    entry['url'] = 'https://raw.githubusercontent.com/gfloxe/BLIXWOU/main/mods/test.jar'
    document = manifest([entry])
    def fetch(url, timeout):
        return io.BytesIO(json.dumps(document).encode() if 'manifest.json' in url else b'data')
    monkeypatch.setattr(pack_mirror, 'urlopen', fetch)
    pack_mirror.refresh(tmp_path)
    published = (tmp_path / 'manifest.json').read_bytes()
    result = json.loads(published)
    assert result['files'][0]['fallbackUrl'] == entry['url']
    assert result['files'][0]['url'] == pack_mirror.PUBLIC + '/pack/objects/' + entry['sha256']
    # A failed update must not replace the previous complete snapshot.
    (tmp_path / 'objects' / entry['sha256']).write_bytes(b'bad')
    monkeypatch.setattr(pack_mirror, 'urlopen', lambda url, timeout: io.BytesIO(json.dumps(document).encode() if 'manifest.json' in url else b'bad!'))
    with pytest.raises(ValueError, match='integrity'):
        pack_mirror.refresh(tmp_path)
    assert (tmp_path / 'manifest.json').read_bytes() == published
