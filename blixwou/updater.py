"""WinSparkle native update engine; update authenticity via pinned Ed25519 key."""
import base64
import ctypes
from .config import LauncherError, resource
from .network import https_url


class LauncherUpdater:
    def __init__(self, config, version, can_shutdown, request_shutdown):
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
            "win_sparkle_check_update_without_ui": [],
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
        dll.win_sparkle_set_app_details("gfloxe", "BLIXWOU", version)
        dll.win_sparkle_set_appcast_url(url.encode("utf-8"))
        if dll.win_sparkle_set_eddsa_public_key(config["ed25519PublicKey"].encode("ascii")) != 1:
            raise LauncherError("WinSparkle a refusé la clé publique de mise à jour.")
        dll.win_sparkle_set_lang(b"fr")
        dll.win_sparkle_set_automatic_check_for_updates(1)
        dll.win_sparkle_init()
        dll.win_sparkle_check_update_without_ui()
        self.dll = dll

    def close(self):
        if self.dll:
            self.dll.win_sparkle_cleanup()
            self.dll = None
