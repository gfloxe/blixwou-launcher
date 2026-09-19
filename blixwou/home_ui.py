"""Presentation helpers for the launcher home, independent of game operations."""
import ctypes
import json
import time
from datetime import datetime

from PySide6.QtCore import Qt, QVariantAnimation
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect

from .config import atomic_json, LauncherError
from .network import request


def dark_titlebar(window):
    try:
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        setter.restype = ctypes.c_long
        value = ctypes.c_int(1)
        for attribute in (20, 19):
            if setter(int(window.winId()), attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except (AttributeError, OSError):
        pass


class GlowButton(QPushButton):
    def __init__(self, text=''):
        super().__init__(text)
        self.halo = QGraphicsDropShadowEffect(self)
        self.halo.setOffset(0, 0)
        self.halo.setBlurRadius(18)
        self.halo.setColor(QColor(166, 103, 255, 0))
        self.setGraphicsEffect(self.halo)
        self.fade = QVariantAnimation(self)
        self.fade.setDuration(180)
        self.fade.valueChanged.connect(lambda value: self.halo.setColor(QColor(166, 103, 255, int(value))))

    def animate(self, target):
        self.fade.stop()
        self.fade.setStartValue(self.halo.color().alpha())
        self.fade.setEndValue(target)
        self.fade.start()

    def enterEvent(self, event):
        self.animate(145)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animate(0)
        super().leaveEvent(event)


def skin_head(root):
    from .skins import Wardrobe
    wardrobe = Wardrobe(root)
    try:
        active = next((entry for entry in wardrobe.entries() if entry.get('active')), None)
    except (LauncherError, OSError, ValueError):
        active = None
    skin = QImage(str(wardrobe.path(active))) if active else QImage()
    head = QImage(8, 8, QImage.Format_ARGB32)
    head.fill(QColor('#b88a6e'))
    painter = QPainter(head)
    if not skin.isNull():
        painter.drawImage(0, 0, skin.copy(8, 8, 8, 8))
        painter.drawImage(0, 0, skin.copy(40, 8, 8, 8))
    else:
        painter.fillRect(0, 0, 8, 2, QColor('#47332b'))
        painter.fillRect(0, 2, 1, 2, QColor('#47332b'))
        painter.fillRect(7, 2, 1, 2, QColor('#47332b'))
        for x in (1, 5):
            painter.fillRect(x, 4, 2, 1, QColor('#ece5df'))
            painter.fillRect(x + 1, 4, 1, 1, QColor('#6264ae'))
        painter.fillRect(2, 6, 4, 2, QColor('#694539'))
    painter.end()
    return QPixmap.fromImage(head.scaled(48, 48, Qt.IgnoreAspectRatio, Qt.FastTransformation))


def normalize_news(items):
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict) or item.get('draft') or item.get('prerelease'):
            continue
        title = item.get('name') or item.get('tag_name')
        date = item.get('published_at')
        if not isinstance(title, str) or not isinstance(date, str):
            continue
        try:
            datetime.fromisoformat(date.replace('Z', '+00:00'))
        except ValueError:
            continue
        body = item.get('body') or ''
        note = ' '.join(str(body).split())
        result.append(dict(name=title[:60], published_at=date, body=note[:137] + '…' if len(note) > 140 else note))
    return sorted(result, key=lambda item: item['published_at'], reverse=True)[:1]


def cached_news(root):
    try:
        path = root / 'news.json'
        if path.stat().st_size > 262144:
            return []
        return normalize_news(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return []


def fetch_news(root):
    try:
        started = time.monotonic()
        with request('GET', 'https://api.github.com/repos/gfloxe/blixwou-launcher/releases?per_page=1',
                     timeout=5, stream=True, headers={'Accept': 'application/vnd.github+json'}) as response:
            body = bytearray()
            for chunk in response.iter_content(16384):
                body.extend(chunk)
                if len(body) > 262144 or time.monotonic() - started > 5:
                    raise ValueError('News response exceeds bounds')
        items = normalize_news(json.loads(body))
        if items:
            atomic_json(root / 'news.json', items)
        return items or cached_news(root)
    except Exception:
        return cached_news(root)
