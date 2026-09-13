"""WinSparkle native update engine; update authenticity via pinned Ed25519 key."""
import base64
import ctypes
import re
import time
import xml.etree.ElementTree as ET
from .config import LauncherError, resource
from .network import https_url, request


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", value):
        raise ValueError("Version X.Y.Z attendue")
    return tuple(map(int, value.split('.')))


def available_update(url, current):
    """Fail open for playing, never for installing: WinSparkle verifies the binary."""
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
        ns = '{http://www.andymatuschak.org/xml-namespaces/sparkle}'
        for item in root.findall('./channel/item'):
            value = item.findtext(ns + 'version')
            enclosure = item.find('enclosure')
            if enclosure is None:
                continue
            value = value or enclosure.get(ns + 'version')
            if version_tuple(value) > current_version:
                https_url(enclosure.attrib['url'])
                if len(base64.b64decode(enclosure.attrib[ns+'edSignature'], validate=True)) == 64:
                    found.append(value)
        return max(found, key=version_tuple) if found else None
    except Exception:
        return None


class LauncherUpdater:
    def __init__(self, config, version, can_shutdown, request_shutdown, on_error=lambda: None, on_cancelled=lambda: None, *, identity=('gfloxe', 'BLIXWOU')):
        self.dll = None
        if not config.get("appcastUrl") and not config.get("ed25519PublicKey"):
            return
        url = https_url(config.get("appcastUrl"))
        try:
            if len(base64.b64decode(config["ed25519PublicKey"], validate=True)) != 32:
                raise ValueError()
        except (KeyError, ValueError):
            raise LauncherError("La clé publique Ed25519 du launcher est invalide.") from None
        path = resource("vendor/WinSparkle.dll")
        if not path.is_file():
            raise LauncherError("WinSparkle.dll manque ; reconstruisez la distribution du launcher.")
        dll = ctypes.CDLL(str(path))
        signatures = {
            "win_sparkle_set_appcast_url": [ctypes.c_char_p],
            "win_sparkle_set_eddsa_public_key": [ctypes.c_char_p],
            "win_sparkle_set_app_details": [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p],
            "win_sparkle_set_lang": [ctypes.c_char_p],
            "win_sparkle_init": [], "win_sparkle_cleanup": [],
            "win_sparkle_set_automatic_check_for_updates": [ctypes.c_int],
            "win_sparkle_check_update_with_ui_and_install": [],
        }
        for name, args in signatures.items():
            getattr(dll, name).argtypes = args
            getattr(dll, name).restype = None
        dll.win_sparkle_set_eddsa_public_key.restype = ctypes.c_int
        self.can_cb = ctypes.CFUNCTYPE(ctypes.c_int)(lambda: int(can_shutdown()))
        self.shutdown_cb = ctypes.CFUNCTYPE(None)(request_shutdown)
        dll.win_sparkle_set_can_shutdown_callback.argtypes = [type(self.can_cb)]
        dll.win_sparkle_set_shutdown_request_callback.argtypes = [type(self.shutdown_cb)]
        dll.win_sparkle_set_can_shutdown_callback(self.can_cb)
        dll.win_sparkle_set_shutdown_request_callback(self.shutdown_cb)
        self.error_cb = ctypes.CFUNCTYPE(None)(on_error)
        self.cancelled_cb = ctypes.CFUNCTYPE(None)(on_cancelled)
        for name, callback in [('win_sparkle_set_error_callback', self.error_cb),
                               ('win_sparkle_set_update_cancelled_callback', self.cancelled_cb),
                               ('win_sparkle_set_did_not_find_update_callback', self.cancelled_cb)]:
            getattr(dll, name).argtypes = [type(callback)]
            getattr(dll, name).restype = None
            getattr(dll, name)(callback)
        dll.win_sparkle_set_app_details(*identity, version)
        dll.win_sparkle_set_appcast_url(url.encode("utf-8"))
        if dll.win_sparkle_set_eddsa_public_key(config["ed25519PublicKey"].encode("ascii")) != 1:
            raise LauncherError("WinSparkle a refusé la clé publique de mise à jour.")
        dll.win_sparkle_set_lang(b"fr")
        dll.win_sparkle_set_automatic_check_for_updates(0)
        dll.win_sparkle_init()
        self.dll = dll

    def install(self):
        if self.dll:
            self.dll.win_sparkle_check_update_with_ui_and_install()

    def close(self):
        if self.dll:
            self.dll.win_sparkle_cleanup()
            self.dll = None
