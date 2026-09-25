"""Public, server-only gateway for the Minecraft menu; no account routes."""
from http import HTTPStatus
import json

from .api import APIError, Service


class ServerGateway:
    def __init__(self, folder):
        self.service = Service(folder)

    def __call__(self, env, start_response):
        method, path = env.get('REQUEST_METHOD'), env.get('PATH_INFO')
        try:
            if (method, path) == ('GET', '/health'):
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
          max_request_body_size=0, max_request_header_size=8192, channel_timeout=15)


if __name__ == '__main__':
    main()
