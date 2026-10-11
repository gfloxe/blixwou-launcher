"""Atomic, content-addressed copy of the public GitHub pack (no credentials)."""
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.request import urlopen
from urllib.parse import urlsplit

SOURCE = 'https://raw.githubusercontent.com/gfloxe/BLIXWOU/main/manifest.json'
PUBLIC = 'https://debian-machine.tail7d0337.ts.net:8443'
FOLDER = Path.home() / 'BLIXWOU-Services' / 'pack'


def github_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'raw.githubusercontent.com'
            or not parsed.path.startswith('/gfloxe/BLIXWOU/') or parsed.username or parsed.password):
        raise ValueError('Unexpected pack source')


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def refresh(folder=FOLDER):
    import time
    with urlopen(SOURCE + '?mirror=' + str(int(time.time())), timeout=30) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('Manifest too large')
    manifest = json.loads(raw)
    if manifest.get('schemaVersion') != 1 or not isinstance(manifest.get('files'), list):
        raise ValueError('Invalid manifest')
    objects = folder / 'objects'
    objects.mkdir(parents=True, exist_ok=True)
    for item in manifest['files']:
        sha, size, url = item['sha256'], item['size'], item['url']
        if not re.fullmatch('[0-9a-f]{64}', sha) or type(size) is not int or not 0 <= size <= 8 * 1024**3:
            raise ValueError('Invalid file metadata')
        github_url(url)
        target = objects / sha
        if not target.is_file() or target.stat().st_size != size or checksum(target) != sha:
            partial = objects / (sha + '.part')
            try:
                with urlopen(url, timeout=60) as response, partial.open('wb') as output:
                    received = 0
                    while chunk := response.read(1024 * 1024):
                        received += len(chunk)
                        if received > size:
                            raise ValueError('File exceeds expected size')
                        output.write(chunk)
                if received != size or checksum(partial) != sha:
                    raise ValueError('File integrity check failed')
                os.replace(partial, target)
            finally:
                partial.unlink(missing_ok=True)
        item['fallbackUrl'] = url
        item['url'] = PUBLIC + '/pack/objects/' + sha
    # Old objects stay available for clients still installing a previous manifest.
    temporary = folder / 'manifest.tmp'
    temporary.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, folder / 'manifest.json')
    print('Pack mirror ready:', manifest['packVersion'], len(manifest['files']), 'files')


if __name__ == '__main__':
    refresh()
