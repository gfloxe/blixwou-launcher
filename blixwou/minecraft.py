"""Official Mojang metadata + NeoForge installer; launcher-lib for rules/arguments."""
import ctypes
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import threading
import zipfile

import minecraft_launcher_lib
from minecraft_launcher_lib import install, command

from .config import LauncherError, atomic_json, read_json, load_config
from .java import ensure_java, HIDDEN
from .network import download, get_json, request, digest, https_url
from .process_guard import require_game_stopped, record_game

MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
NEOFORGE_VERSIONS = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"


def within(root, path):
    base, target = Path(root).resolve(), Path(path)
    if not target.resolve().is_relative_to(base):
        raise LauncherError("Chemin Minecraft en dehors du dossier dédié.")
    current = target
    while current != base and current != current.parent:
        if current.is_symlink() or current.is_junction():
            raise LauncherError("Jonction interdite dans l’installation Minecraft.")
        current = current.parent
    if Path(root).is_symlink() or Path(root).is_junction():
        raise LauncherError("Le dossier Minecraft ne doit pas être une jonction.")
    return target


def library_downloader(url, path, callback=None, sha1=None, lzma_compressed=False, session=None, minecraft_directory=None, overwrite=False):
    """Adapter pinned to launcher-lib 8.0, replacing its non-atomic downloader."""
    target = Path(path)
    if minecraft_directory is not None:
        within(minecraft_directory, target)
    if lzma_compressed:
        raise LauncherError("Format de téléchargement non attendu pour Minecraft 1.21.1.")
    if not sha1:
        # Maven coordinates without embedded hashes use the publisher's sidecar.
        with request("GET", url + ".sha1") as response:
            sha1 = response.text.strip().split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{40}", sha1):
        raise LauncherError("Empreinte officielle Minecraft invalide.")
    download(url, target, sha1, algorithm="sha1")
    return True


def prepare_minecraft(root, manifest, settings, progress):
    versions = manifest["versions"]
    neo = versions["neoforge"]
    if versions["minecraft"] != "1.21.1" or versions["java"] != 21 or not re.fullmatch(r"21\.1\.\d+(?:-beta)?", neo or ""):
        raise LauncherError("Le trio Minecraft / NeoForge / Java est incompatible ou incomplet.")
    progress("Vérification des versions officielles", 0, 0)
    official = get_json(MOJANG_MANIFEST)
    mc = next((v for v in official["versions"] if v["id"] == versions["minecraft"]), None)
    if mc is None or neo not in get_json(NEOFORGE_VERSIONS)["versions"]:
        raise LauncherError("La version demandée n’existe pas dans les catalogues officiels.")
    java = ensure_java(root, settings["javaPath"], progress)
    # Keep libraries/assets separate from user saves and managed pack files.
    engine = root / "minecraft"
    engine.mkdir(parents=True, exist_ok=True)
    descriptor = engine / "versions" / "1.21.1" / "1.21.1.json"
    within(engine, descriptor)
    download(mc["url"], descriptor, mc["sha1"], algorithm="sha1")
    metadata = read_json(descriptor)
    if metadata.get("javaVersion", {}).get("majorVersion") != 21:
        raise LauncherError("Le catalogue Mojang ne confirme pas Java 21. Installation arrêtée.")

    # Only this module's download hook is changed; no global requests monkeypatch.
    install.download_file = library_downloader
    install.check_path_inside_minecraft_directory = within
    maximum = [0]
    phase = ["Vérification de Minecraft"]
    translations = {"Download Libraries": "Bibliothèques Minecraft", "Download Assets": "Ressources Minecraft"}
    def status(message):
        phase[0] = translations.get(message, "Installation Minecraft")
        maximum[0] = 0
        progress(phase[0], 0, 0)
    def set_max(value):
        maximum[0] = max(0, value + 1)  # library 8.0 emits total minus one
    callbacks = {"setStatus": status, "setMax": set_max, "setProgress": lambda n: progress(phase[0], n, maximum[0])}
    install.install_libraries("1.21.1", metadata["libraries"], str(engine), callbacks, max_workers=8)
    install.install_assets(metadata, str(engine), callbacks, max_workers=8)
    client = metadata["downloads"]["client"]
    download(client["url"], descriptor.with_suffix(".jar"), client["sha1"], client["size"], lambda n,t: progress("Téléchargement de Minecraft 1.21.1", n,t), algorithm="sha1")
    if metadata.get("logging", {}).get("client"):
        log = metadata["logging"]["client"]["file"]
        log_path = within(engine, engine / "assets" / "log_configs" / log["id"])
        download(log["url"], log_path, log["sha1"], log["size"], algorithm="sha1")

    version_id = "neoforge-" + neo
    marker_path = root / "neoforge-installed.json"
    marker = read_json(marker_path, {})
    healthy = marker.get("version") == neo and bool(marker.get("files"))
    if healthy:
        progress("Vérification de NeoForge", 0, 0)
        for relative, expected in marker["files"].items():
            file = within(engine, engine / relative)
            if not file.is_file() or digest(file) != expected:
                healthy = False
                break
    if not healthy:
        url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{neo}/neoforge-{neo}-installer.jar"
        with request("GET", url + ".sha256") as response:
            checksum = response.text.strip().split()[0].lower()
        if not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise LauncherError("L’empreinte officielle de NeoForge est invalide.")
        jar = root / "downloads" / f"neoforge-{neo}-installer.jar"
        download(url, jar, checksum, progress=lambda n,t: progress("Téléchargement de NeoForge " + neo, n,t))
        with zipfile.ZipFile(jar) as archive:
            profile = json.loads(archive.read("install_profile.json"))
            if profile.get("minecraft") != "1.21.1":
                raise LauncherError("L’installateur NeoForge cible une autre version de Minecraft.")
        profiles = engine / "launcher_profiles.json"
        if not profiles.exists():
            atomic_json(profiles, {"profiles": {}})
        progress("Installateur officiel NeoForge · traitement en cours", 0, 0)
        work = root / "installer-work"
        work.mkdir(exist_ok=True)
        logs = root / "logs"
        logs.mkdir(exist_ok=True)
        with (logs / "neoforge-installer.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run([java, "-Dsun.net.client.defaultConnectTimeout=15000", "-Dsun.net.client.defaultReadTimeout=45000", "-jar", str(jar), "--install-client", str(engine)], cwd=work, stdout=log, stderr=subprocess.STDOUT, timeout=1200, creationflags=HIDDEN)
            except subprocess.TimeoutExpired:
                raise LauncherError("L’installation NeoForge a dépassé vingt minutes. Consultez les journaux puis réessayez.") from None
        if result.returncode:
            raise LauncherError("L’installateur officiel NeoForge a échoué. Consultez neoforge-installer.log puis réessayez.")
        installed = engine / "versions" / version_id / (version_id + ".json")
        neo_metadata = read_json(installed, {})
        if neo_metadata.get("inheritsFrom") != "1.21.1":
            raise LauncherError("Le profil NeoForge installé ne correspond pas à Minecraft 1.21.1.")
        # Validate published hashes after the official installer, including repair.
        install.install_libraries(version_id, neo_metadata["libraries"], str(engine), callbacks, max_workers=8)
        inventory = {}
        for folder in (engine / "libraries", engine / "versions" / version_id):
            for file in folder.rglob("*"):
                if file.is_file() and file.suffix != ".part":
                    within(engine, file)
                    inventory[file.relative_to(engine).as_posix()] = digest(file)
        atomic_json(marker_path, {"version": neo, "files": inventory})
    progress("Minecraft et NeoForge prêts", 1, 1)
    return java, version_id


def build_command(root, version_id, java, settings, profile, server):
    options = {
        "username": profile["name"], "uuid": profile["id"], "token": profile["access_token"],
        "executablePath": java, "gameDirectory": str(root / "game"),
        "jvmArguments": [
            f"-Xms{settings['ramMb']}M", f"-Xmx{settings['ramMb']}M",
            "-XX:+UseG1GC", "-XX:+UnlockExperimentalVMOptions", "-XX:+ParallelRefProcEnabled",
            "-XX:MaxGCPauseMillis=40", "-XX:G1NewSizePercent=25", "-XX:G1MaxNewSizePercent=50",
            "-XX:G1HeapRegionSize=16M", "-XX:G1ReservePercent=20", "-XX:G1MixedGCCountTarget=3",
            "-XX:InitiatingHeapOccupancyPercent=20", "-XX:G1MixedGCLiveThresholdPercent=90",
            "-XX:SurvivorRatio=32", "-XX:MaxTenuringThreshold=1", "-XX:+PerfDisableSharedMem",
        ],
        "launcherName": "BLIXWOU", "launcherVersion": load_config()["appVersion"],
        "customResolution": True, "resolutionWidth": str(settings["width"]), "resolutionHeight": str(settings["height"]),
    }
    args = command.get_minecraft_command(version_id, str(root / "minecraft"), options)
    # launcher-lib 8.0 omits these modern optional placeholders.
    # Empty offline values carry no Microsoft identity; MSA values come from OAuth/XSTS.
    args = [arg.replace("${clientid}", profile.get("client_id", "")).replace("${auth_xuid}", profile.get("xuid", "")) for arg in args]
    if any("${" in arg for arg in args):
        raise LauncherError("Les arguments officiels contiennent un paramètre non pris en charge. Mettez à jour le launcher.")
    # launcher-lib defaults to msa for all sessions; keep offline identity explicit.
    if "--userType" in args:
        args[args.index("--userType") + 1] = "msa" if profile["mode"] == "microsoft" else "legacy"
    return args


class GameSession:
    def __init__(self):
        self.process = None
        self.stopping = False

    def stop(self):
        process = self.process
        if process is None or process.poll() is not None or self.stopping:
            return
        self.stopping = True
        def close():
            # Ask only windows owned by the process launched by this session to close.
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
                user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
                user32.IsWindowVisible.argtypes = [wintypes.HWND]
                user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                @callback_type
                def visit(hwnd, param):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == process.pid and user32.IsWindowVisible(hwnd):
                        user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                    return True
                user32.EnumWindows(visit, 0)
            else:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
        threading.Thread(target=close, name='BLIXWOU-stop-game', daemon=True).start()


def ready_game_title(title):
    name = title.casefold()
    return 'minecraft' in name and not any(word in name for word in ('loading', 'chargement'))


def game_window_ready(process):
    """Wait for the Minecraft window title to leave NeoForge's loading screen."""
    if os.name != 'nt' or process is None or process.poll() is not None:
        return False
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    ready = False

    @callback_type
    def visit(hwnd, param):
        nonlocal ready
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != process.pid or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if ready_game_title(title.value):
            ready = True
            return False
        return True

    user32.EnumWindows(visit, 0)
    return ready


def launch_game(root, args, profile, progress, session=None):
    require_game_stopped(root)
    (root / "game").mkdir(exist_ok=True)
    secrets = [profile.get("access_token", ""), profile.get("refresh_token", "")]
    progress("Démarrage de Minecraft", 0, 0)
    # Never log the command line. The launcher remains alive and keeps its lock.
    process = subprocess.Popen(args, cwd=root / "game", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=HIDDEN)
    record_game(root, process)
    if session is not None:
        session.stopping = False
        session.process = process
    progress("Minecraft est lancé", 0, 0)
    with (root / "logs" / "game-console.log").open("w", encoding="utf-8") as log:
        for line in process.stdout:
            for secret in secrets:
                if len(secret) > 8:
                    line = line.replace(secret, "[SECRET MASQUÉ]")
            if re.search(r"access.?token|refresh.?token|authorization|identityToken", line, re.I):
                line = "[Ligne contenant des données de connexion masquée]\n"
            log.write(line)
            log.flush()
    code = process.wait()
    (root / "active-game.json").unlink(missing_ok=True)
    stopped = session is not None and session.stopping
    if session is not None:
        session.process = None
    if code and not stopped:
        raise LauncherError(f"Minecraft s’est arrêté avec le code {code}. Consultez les journaux du jeu.")
    return code
