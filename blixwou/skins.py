"""Local wardrobe and bounded public skin imports; no account credentials."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit
from uuid import uuid4

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter

from .config import LauncherError, atomic_json, read_json
from .network import get_json, https_url, request

LIMIT = 32768


def png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise LauncherError("Impossible d’enregistrer le skin PNG.")
    return bytes(data)


def normalize_png(data):
    if len(data) > LIMIT or len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise LauncherError("Choisissez un PNG de 32 Ko maximum, en 64×64 ou 64×32.")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) not in ((64, 64), (64, 32)):
        raise LauncherError("Le skin doit mesurer 64×64 ou 64×32 pixels.")
    source = QImage.fromData(data, "PNG").convertToFormat(QImage.Format_RGBA8888)
    if source.isNull() or source.width() != width or source.height() != height:
        raise LauncherError("Ce fichier PNG est endommagé.")
    if height == 32:
        result = QImage(64, 64, QImage.Format_RGBA8888)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.drawImage(0, 0, source)
        # Mirror each right limb face into the modern left limb UV layout.
        for sx, sy, w, h, dx, dy in [
            (4,16,4,4,20,48),(8,16,4,4,24,48),(8,20,4,12,16,52),
            (4,20,4,12,20,52),(0,20,4,12,24,52),(12,20,4,12,28,52),
            (44,16,4,4,36,48),(48,16,4,4,40,48),(48,20,4,12,32,52),
            (44,20,4,12,36,52),(40,20,4,12,40,52),(52,20,4,12,44,52),
        ]:
            painter.drawImage(dx, dy, source.copy(sx, sy, w, h).flipped(Qt.Horizontal))
        painter.end()
        # Legacy skins commonly have an opaque unused hat area.
        if all(source.pixelColor(x,y).alpha() == 255 for x in range(32,64) for y in range(16)):
            for x in range(32,64):
                for y in range(16):
                    result.setPixelColor(x,y,Qt.transparent)
        source = result
    # Vanilla base layers must be opaque, while outer layers retain transparency.
    for x0,y0,x1,y1 in [(0,0,32,16),(0,16,64,32),(16,48,48,64)]:
        for x in range(x0,x1):
            for y in range(y0,y1):
                color = source.pixelColor(x,y)
                color.setAlpha(255)
                source.setPixelColor(x,y,color)
    result = png_bytes(source)
    if len(result) > LIMIT:
        raise LauncherError("Le PNG converti dépasse 32 Ko.")
    return result


def atomic_png(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.png.tmp')
    with temp.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


class Wardrobe:
    def __init__(self, root):
        self.folder = Path(root) / 'skins'
        self.index = self.folder / 'skins.json'

    def entries(self):
        entries = read_json(self.index, [])
        if not isinstance(entries, list) or any(
            not re.fullmatch(r'[0-9a-f]{32}', e.get('id', '')) or e.get('model') not in ('classic','slim')
            for e in entries
        ):
            raise LauncherError("L’index de la garde-robe est invalide.")
        return entries

    def path(self, entry):
        if not re.fullmatch(r'[0-9a-f]{32}', entry['id']):
            raise LauncherError("Identifiant de skin invalide.")
        return self.folder / (entry['id'] + '.png')

    def add(self, data, name, model='classic'):
        if model not in ('classic','slim'):
            raise LauncherError("Modèle de skin invalide.")
        data = normalize_png(data)
        entries = self.entries()
        entry = dict(id=uuid4().hex, name=name.strip()[:64] or 'Mon skin', model=model,
                     date=datetime.now(timezone.utc).isoformat(), active=not entries)
        atomic_png(self.path(entry), data)
        try:
            atomic_json(self.index, entries + [entry])
        except Exception:
            self.path(entry).unlink(missing_ok=True)
            raise
        return entry

    def edit(self, ident, **changes):
        if set(changes) - {'name','model','active'} or changes.get('model','classic') not in ('classic','slim'):
            raise LauncherError("Modification de skin invalide.")
        entries = self.entries()
        target = next(e for e in entries if e['id'] == ident)
        if changes.get('active'):
            for entry in entries:
                entry['active'] = False
        if 'name' in changes:
            changes['name'] = changes['name'].strip()[:64] or 'Mon skin'
        target.update(changes)
        atomic_json(self.index, entries)

    def delete(self, ident):
        entries = self.entries()
        target = next(e for e in entries if e['id'] == ident)
        atomic_json(self.index, [e for e in entries if e['id'] != ident])
        self.path(target).unlink(missing_ok=True)

    def export_active(self, game):
        folder = Path(game) / 'config' / 'blixwou-skin'
        for parent in (Path(game), Path(game)/'config', folder):
            if parent.is_symlink() or parent.is_junction():
                raise LauncherError("Lien interdit dans le dossier du skin actif.")
        active = next((e for e in self.entries() if e['active']), None)
        if active is None:
            (folder/'active.json').unlink(missing_ok=True)
            (folder/'active.png').unlink(missing_ok=True)
            return
        data = normalize_png(self.path(active).read_bytes())
        atomic_png(folder/'active.png', data)
        atomic_json(folder/'active.json', {'model': active['model']})


def import_premium(name):
    if not re.fullmatch(r'[A-Za-z0-9_]{3,16}', name):
        raise LauncherError("Le pseudo premium doit contenir 3 à 16 lettres, chiffres ou underscores.")
    profile = get_json('https://api.mojang.com/users/profiles/minecraft/' + name)
    ident = profile.get('id','')
    if not re.fullmatch(r'[0-9a-fA-F]{32}', ident):
        raise LauncherError("Ce profil premium est introuvable.")
    session = get_json('https://sessionserver.mojang.com/session/minecraft/profile/' + ident)
    try:
        value = next(p['value'] for p in session['properties'] if p['name'] == 'textures')
        skin = json.loads(base64.b64decode(value, validate=True))['textures']['SKIN']
        parsed = urlsplit(skin['url'])
        if parsed.hostname != 'textures.minecraft.net' or parsed.port not in (None,443) or parsed.username or parsed.password or parsed.scheme not in ('https','http'):
            raise ValueError()
        url = https_url('https://textures.minecraft.net' + parsed.path)
        model = skin.get('metadata',{}).get('model','classic')
        if model not in ('classic','slim'):
            raise ValueError()
    except (KeyError, ValueError, StopIteration):
        raise LauncherError("Ce profil ne fournit pas de skin Mojang valide.") from None
    class TextureTransport:
        def request(self, method, url, **kwargs):
            # network.request calls this again for every redirect.
            if urlsplit(https_url(url)).netloc != 'textures.minecraft.net':
                raise LauncherError("Le téléchargement doit rester sur textures.minecraft.net.")
            import requests
            return requests.request(method, url, **kwargs)
    with request('GET', url, session=TextureTransport(), stream=True) as response:
        data = bytearray()
        for chunk in response.iter_content(4096):
            data.extend(chunk)
            if len(data) > LIMIT:
                raise LauncherError("Le skin dépasse 32 Ko.")
    return normalize_png(bytes(data)), model
