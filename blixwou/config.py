import json
import os
import sys
from pathlib import Path


class LauncherError(Exception):
    """Message safe to show to the user, never containing credentials."""


def resource(name: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / name


def data_root() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "BLIXWOU"


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def load_config():
    config = read_json(resource("launcher-config.json"))
    if config["minecraft"] != "1.21.1" or config["javaMajor"] != 21:
        raise LauncherError("Cette édition de BLIXWOU nécessite Minecraft 1.21.1 et Java 21.")
    return config


DEFAULT_SETTINGS = {"ramMb": 4096, "width": 1280, "height": 720, "javaPath": ""}


def load_settings(root: Path):
    value = DEFAULT_SETTINGS | read_json(root / "settings.json", {})
    if not 2048 <= value["ramMb"] <= 32768:
        value["ramMb"] = 4096
    for key, minimum, maximum in [("width", 854, 7680), ("height", 480, 4320)]:
        if not minimum <= value[key] <= maximum:
            value[key] = DEFAULT_SETTINGS[key]
    return value
