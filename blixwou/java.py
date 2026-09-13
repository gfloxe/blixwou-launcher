import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import zipfile

from .config import LauncherError, atomic_json, read_json
from .network import download, get_json, digest

ADOPTIUM = "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse"
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def validate_java(executable):
    try:
        result = subprocess.run([str(executable), "-XshowSettings:properties", "-version"], capture_output=True, text=True, timeout=20, creationflags=HIDDEN)
        output = result.stderr + result.stdout
        if result.returncode or not re.search(r"java\.version\s*=\s*21(?:\.|\s)", output) or not re.search(r"sun\.arch\.data\.model\s*=\s*64", output):
            raise LauncherError("Sélectionnez un exécutable Java 21 en 64 bits.")
    except (OSError, subprocess.TimeoutExpired):
        raise LauncherError("Impossible d’exécuter le Java sélectionné.") from None
    return str(executable)


def extract_java(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        if sum(f.file_size for f in z.infolist()) > 2 * 1024**3:
            raise LauncherError("Archive Java trop volumineuse.")
        for item in z.infolist():
            parts = item.filename.rstrip("/").split("/")
            if any(p in ("", ".", "..") or ":" in p or "\\" in p for p in parts) or stat.S_ISLNK(item.external_attr >> 16):
                raise LauncherError("Chemin dangereux dans l’archive Java.")
            target = destination.joinpath(*parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise LauncherError("Extraction Java hors du dossier prévu.")
        z.extractall(destination)


def ensure_java(root: Path, custom: str, progress):
    if custom:
        return validate_java(Path(custom))
    runtime = root / "runtime"
    marker = read_json(runtime / "installed.json")
    if marker:
        exe = runtime / marker["executable"]
        if exe.resolve().is_relative_to(runtime.resolve()) and exe.is_file() and digest(exe) == marker["sha256"]:
            try:
                return validate_java(exe)
            except LauncherError:
                pass  # Repair an unusable automatic runtime from its verified archive.
    progress("Recherche de Java 21 · Eclipse Temurin", 0, 0)
    entries = get_json(ADOPTIUM)
    entry = next((e for e in entries if e["binary"]["architecture"] == "x64" and e["version"]["major"] == 21), None)
    if entry is None:
        raise LauncherError("Aucune distribution Java 21 x64 autorisée trouvée.")
    package = entry["binary"]["package"]
    archive = root / "downloads" / (package["checksum"] + ".zip")
    download(package["link"], archive, package["checksum"], package["size"], lambda n, t: progress("Téléchargement de Java 21", n, t))
    # Content-addressed directory: an interrupted extraction is safe to retry.
    folder = runtime / package["checksum"]
    progress("Extraction et vérification de Java 21", 0, 0)
    extract_java(archive, folder)
    exe = next(folder.glob("*/bin/java.exe"), None)
    if exe is None:
        raise LauncherError("Exécutable Java absent de l’archive.")
    validate_java(exe)
    atomic_json(runtime / "installed.json", {"executable": exe.relative_to(runtime).as_posix(), "sha256": digest(exe), "release": entry["release_name"]})
    return str(exe)
