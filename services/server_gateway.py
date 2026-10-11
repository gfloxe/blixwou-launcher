"""Public, server-only gateway for the Minecraft menu; no account routes."""
from http import HTTPStatus
import json
import re
import os
from pathlib import Path

from .api import APIError, Service
from .pack_publish import PackPublisher


class ServerGateway:
    def __init__(self, folder):
        self.service = Service(folder)
        self.pack_folder = Path(folder).parent / 'pack'
        self.publisher = PackPublisher(folder, self.pack_folder)
        self.syncora = None

    def __call__(self, env, start_response):
        method, path = env.get('REQUEST_METHOD'), env.get('PATH_INFO')
        if path == '/syncora' or (path or '').startswith('/syncora/'):
            if self.syncora is None:
                from .syncora_admin import Syncora
                self.syncora = Syncora(self.pack_folder.parent.parent / 'Syncora', self.pack_folder.parent)
            return self.syncora(env, start_response)
        if method == 'GET' and (path == '/pack/manifest.json' or re.fullmatch(r'/pack/objects/[0-9a-f]{64}', path or '')):
            target = self.pack_folder / ('manifest.json' if path == '/pack/manifest.json' else 'objects/' + path.rsplit('/', 1)[1])
            try:
                stream = target.open('rb')
            except OSError:
                start_response('503 Service Unavailable', [('Content-Length', '0')])
                return [b'']
            start_response('200 OK', [('Content-Type', 'application/json' if path.endswith('.json') else 'application/octet-stream'),
                                     ('Content-Length', str(os.fstat(stream.fileno()).st_size)),
                                     ('Cache-Control', 'no-cache' if path.endswith('.json') else 'public, max-age=31536000, immutable'),
                                     ('X-Content-Type-Options', 'nosniff')])
            def chunks():
                with stream:
                    while block := stream.read(256 * 1024):
                        yield block
            return chunks()
        try:
            if path == '/v1/pack/files':
                code, result = 200, self.publisher.handle(env)
            elif (method, path) == ('GET', '/health'):
                code, result = 200, {'service': 'BLIXWOU server gateway', 'ok': True}
            elif (method, path) == ('GET', '/v1/server/status'):
                code, result = 200, self.service.status()
            elif (method, path) == ('POST', '/v1/server/start'):
                if env.get('HTTP_ORIGIN') or env.get('CONTENT_LENGTH') not in (None, '', '0'):
                    raise APIError(400, 'Requête invalide.')
                code, result = 202, self.service.start_server()
            else:
                raise APIError(404, 'Route introuvable.')
        except APIError as error:
            code, result = error.status, {'error': error.message}
        except Exception:
            code, result = 503, {'error': 'Service temporairement indisponible.'}
        payload = json.dumps(result, ensure_ascii=False).encode('utf-8')
        start_response(f'{code} {HTTPStatus(code).phrase}', [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Content-Length', str(len(payload))), ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff')])
        return [payload]


def main():
    import os
    from pathlib import Path
    from waitress import serve
    os.umask(0o077)
    gateway = ServerGateway(Path.home() / 'BLIXWOU-Services' / 'private')
    serve(gateway, listen='127.0.0.1:8767', threads=4, connection_limit=50,
          max_request_body_size=51 * 1024 * 1024, max_request_header_size=8192, channel_timeout=60)


if __name__ == '__main__':
    main()
