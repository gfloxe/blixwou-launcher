"""Bounded HTTPS requests and atomic, integrity-checked downloads."""
import hashlib
import os
import time
import threading
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from .config import LauncherError


_download_transport = threading.local()


def download_session():
    """One connection pool per download worker; never shared with OAuth requests."""
    session = getattr(_download_transport, "session", None)
    if session is None:
        session = requests.Session()
        _download_transport.session = session
    # Public file downloads do not need persistent website cookies.
    session.cookies.clear()
    return session


def https_url(url: str) -> str:
    if not isinstance(url, str):
        raise LauncherError("Une URL HTTPS doit être renseignée.")
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment:
        raise LauncherError("Adresse refusée : HTTPS sans identifiants est obligatoire.")
    return url


def request(method, url, *, session=None, timeout=(10, 45), **kwargs):
    """Validate every redirect before connecting; never downgrade TLS."""
    for _ in range(6):
        https_url(url)
        send = session.request if session is not None else requests.request
        response = send(method, url, timeout=timeout, allow_redirects=False, **kwargs)
        if response.status_code in (301, 302, 303, 307, 308):
            target = urljoin(url, response.headers.get("Location", ""))
            response.close()
            if method != "GET" or any(k.lower() == "authorization" for k in kwargs.get("headers", {})):
                raise LauncherError("Redirection inattendue pendant l’authentification.")
            url = target
            continue
        try:
            response.raise_for_status()
        except requests.HTTPError:
            response.close()
            raise
        return response
    raise LauncherError("Trop de redirections réseau.")


def get_json(url: str):
    with request("GET", url, stream=True) as r:
        content = bytearray()
        for chunk in r.iter_content(65536):
            content.extend(chunk)
            if len(content) > 8 * 1024 * 1024:
                raise LauncherError("Document distant trop volumineux.")
        import json
        return json.loads(content)


def digest(path: Path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, target: Path, checksum: str, size=None, progress=lambda n, t: None, algorithm="sha256"):
    https_url(url)
    if target.is_file() and (size is None or target.stat().st_size == size) and digest(target, algorithm) == checksum:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    for attempt in range(3):
        try:
            start = partial.stat().st_size if partial.exists() else 0
            if size is not None and start > size:
                partial.unlink()
                start = 0
            headers = {"Accept-Encoding": "identity"}
            if start:
                headers["Range"] = f"bytes={start}-"
            with request("GET", url, headers=headers, stream=True, session=download_session()) as r:
                if start and r.status_code == 206:
                    if not r.headers.get("Content-Range", "").startswith(f"bytes {start}-"):
                        raise LauncherError("Reprise du téléchargement incohérente.")
                    mode = "ab"
                else:
                    start, mode = 0, "wb"
                received = start
                total = size or (int(r.headers.get("Content-Length", 0)) + start)
                with partial.open(mode) as f:
                    for chunk in r.iter_content(256 * 1024):
                        received += len(chunk)
                        if size is not None and received > size:
                            raise LauncherError("Taille du fichier téléchargé incorrecte.")
                        f.write(chunk)
                        progress(received, total)
                    f.flush()
                    os.fsync(f.fileno())
            if (size is not None and received != size) or digest(partial, algorithm) != checksum:
                partial.unlink(missing_ok=True)
                raise LauncherError("Empreinte du fichier incorrecte ; téléchargement refusé.")
            os.replace(partial, target)
            return
        except (requests.RequestException, LauncherError):
            if attempt == 2:
                raise LauncherError("Téléchargement impossible après trois essais. Réessayez ; vos fichiers actifs sont conservés.") from None
            # Invalid Range, changed entity or failed hash: restart when necessary.
            if size is not None and partial.exists() and partial.stat().st_size >= size:
                partial.unlink()
            time.sleep(1 + attempt)
