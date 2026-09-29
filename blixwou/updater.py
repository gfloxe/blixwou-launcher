"""Signed launcher updates with progress reported to the BLIXWOU interface."""
import base64
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

from .config import LauncherError, resource
from .network import https_url, request


NAMESPACE = '{http://www.andymatuschak.org/xml-namespaces/sparkle}'
MAX_INSTALLER_SIZE = 250 * 1024 * 1024
HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str
    size: int
    signature: str


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}', value):
        raise ValueError('Version X.Y.Z attendue')
    return tuple(map(int, value.split('.')))


def fetch_update(url, current):
    """Read bounded RSS metadata; invalid or unavailable feeds never block play."""
    try:
        current_version = version_tuple(current)
        started = time.monotonic()
        with request('GET', https_url(url), timeout=5, stream=True) as response:
            data = bytearray()
            for chunk in response.iter_content(4096):
                data.extend(chunk)
                if len(data) > 131072 or time.monotonic() - started > 5:
                    return None
        if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
            return None
        root = ET.fromstring(data)
        found = []
        for item in root.findall('./channel/item'):
            enclosure = item.find('enclosure')
            if enclosure is None:
                continue
            value = item.findtext(NAMESPACE + 'version') or enclosure.get(NAMESPACE + 'version')
            if version_tuple(value) <= current_version:
                continue
            download_url = https_url(enclosure.attrib['url'])
            signature = enclosure.attrib[NAMESPACE + 'edSignature']
            if len(base64.b64decode(signature, validate=True)) != 64:
                continue
            size = int(enclosure.attrib['length'])
            if not 0 < size <= MAX_INSTALLER_SIZE:
                continue
            found.append(UpdateInfo(value, download_url, size, signature))
        return max(found, key=lambda item: version_tuple(item.version)) if found else None
    except Exception:
        return None


def available_update(url, current):
    info = fetch_update(url, current)
    return info.version if info else None


def verify_installer(path: Path, info: UpdateInfo, public_key: str):
    """Use the publisher's Ed25519 verifier, never trust an unverified download."""
    tool = resource('vendor/winsparkle-tool.exe')
    try:
        if len(base64.b64decode(public_key, validate=True)) != 32 or not tool.is_file():
            raise ValueError()
        result = subprocess.run(
            [str(tool), 'verify', '--public-key', public_key,
             '--signature', info.signature, str(path)],
            capture_output=True, creationflags=HIDDEN, timeout=45, check=False,
        )
        if result.returncode != 0:
            raise ValueError()
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise LauncherError('Signature de la mise à jour invalide. Installation annulée.') from None


def download_verified(root: Path, info: UpdateInfo, public_key: str, progress):
    """Download to a private staging file and promote only after signature checks."""
    folder = root / 'updates'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'BLIXWOU-Setup-{info.version}-x64.exe'
    if target.is_file() and target.stat().st_size == info.size:
        try:
            verify_installer(target, info, public_key)
            progress('Téléchargement déjà vérifié', info.size, info.size)
            return target
        except LauncherError:
            target.unlink()
    partial = target.with_suffix('.download')
    partial.unlink(missing_ok=True)
    received = 0
    try:
        with request('GET', info.url, timeout=(10, 45), stream=True) as response:
            with partial.open('wb') as output:
                for chunk in response.iter_content(256 * 1024):
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > info.size:
                        raise LauncherError('La taille de la mise à jour est incorrecte.')
                    output.write(chunk)
                    progress('Téléchargement du launcher', received, info.size)
                output.flush()
                os.fsync(output.fileno())
        if received != info.size:
            raise LauncherError('Le téléchargement du launcher est incomplet.')
        progress('Vérification de la signature', 0, 0)
        verify_installer(partial, info, public_key)
        os.replace(partial, target)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def start_installer(path: Path):
    """The signed Inno Setup package closes the old launcher and opens the new one."""
    if not path.is_file():
        raise LauncherError('Installateur de mise à jour introuvable.')
    try:
        subprocess.Popen(
            [str(path), '/SILENT', '/SP-', '/NOICONS', '/SUPPRESSMSGBOXES',
             '/CLOSEAPPLICATIONS', '/NORESTART'],
            cwd=path.parent, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=HIDDEN,
        )
    except OSError:
        raise LauncherError('Impossible de démarrer l’installation de la mise à jour.') from None
