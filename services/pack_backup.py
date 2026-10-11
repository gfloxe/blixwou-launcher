"""Copy a Debian publication to GitHub in one atomic, non-forced commit."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import urllib.parse

from .syncora_admin import Syncora


def backup(root=None, services=None):
    root = Path(root or Path.home() / 'Syncora')
    services = Path(services or Path.home() / 'BLIXWOU-Services')
    app = Syncora(root, services)
    token = app.credential('github.token')
    if not token or not (services / 'pack' / 'primary').exists():
        print('GitHub backup waiting for configuration or first Debian publication')
        return
    manifest = app.publisher.snapshot()
    state = root / 'private' / 'backup-version.txt'
    if state.exists() and state.read_text() == manifest['packVersion']:
        return
    base = 'https://api.github.com/repos/gfloxe/BLIXWOU'

    def request(route, method='GET', document=None):
        data = json.dumps(document).encode() if document is not None else None
        return json.loads(app.upstream(base + route, token, method, data))

    ref = request('/git/ref/heads/main')['object']['sha']
    parent = request('/git/commits/' + ref)
    tree = request('/git/trees/' + parent['tree']['sha'] + '?recursive=1')
    if tree.get('truncated'):
        raise RuntimeError('GitHub tree too large; no backup written')
    current = {item['path']: item['sha'] for item in tree['tree'] if item['type'] == 'blob'}
    previous = request('/contents/manifest.json?ref=' + ref)
    previous = json.loads(base64.b64decode(previous['content']))
    entries = []

    def blob(path, data):
        expected = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if current.get(path) == expected:
            return
        sha = request('/git/blobs', 'POST', {'encoding': 'base64',
                                            'content': base64.b64encode(data).decode()})['sha']
        entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': sha})

    exported = copy.deepcopy(manifest)
    for item in exported['files']:
        data = (services / 'pack' / 'objects' / item['sha256']).read_bytes()
        if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise RuntimeError('Corrupt object; backup cancelled')
        blob(item['path'], data)
        item['url'] = 'https://raw.githubusercontent.com/gfloxe/BLIXWOU/main/' + \
                      urllib.parse.quote(item['path'], safe='/')
        item.pop('fallbackUrl', None)
    paths = {f['path'] for f in manifest['files']}
    for item in previous['files']:
        if item['path'] not in paths and item['path'] in current:
            entries.append({'path': item['path'], 'mode': '100644', 'type': 'blob', 'sha': None})
    blob('manifest.json', json.dumps(exported, ensure_ascii=False, indent=2).encode())
    if entries:
        new_tree = request('/git/trees', 'POST', {'base_tree': parent['tree']['sha'], 'tree': entries})['sha']
        commit = request('/git/commits', 'POST', {'message': 'Copie de secours du pack Debian [skip ci]',
                                                 'tree': new_tree, 'parents': [ref]})['sha']
        request('/git/refs/heads/main', 'PATCH', {'sha': commit, 'force': False})
    temporary = state.with_suffix('.tmp')
    temporary.write_text(manifest['packVersion'])
    os.replace(temporary, state)
    print('GitHub backup complete: ' + manifest['packVersion'])


if __name__ == '__main__':
    backup()
