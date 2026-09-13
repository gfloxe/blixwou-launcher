"""Pack validation, managed ownership and crash-recoverable transactions."""
import os
import base64
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, quote

from .config import LauncherError, atomic_json, read_json
from .network import digest, download, get_json, https_url

ROOTS = {"mods", "config", "defaultconfigs", "resourcepacks", "shaderpacks"}
RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)", re.I)


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise LauncherError("Chemin de pack invalide.")
    parts = relative.split("/")
    if len(parts) < 2 or parts[0] not in ROOTS or any(
        p in ("", ".", "..") or p.endswith((".", " ")) or RESERVED.match(p)
        or any(ord(c) < 32 or c in '<>"|?*' for c in p) for p in parts
    ):
        raise LauncherError("Chemin interdit dans le manifeste : " + relative)
    base = root.resolve()
    path = root.joinpath(*PurePosixPath(relative).parts)
    cursor = root
    if root.is_symlink() or root.is_junction():
        raise LauncherError("Le dossier du jeu ne doit pas être une jonction.")
    for part in parts:
        cursor /= part
        if cursor.is_symlink() or cursor.is_junction():
            raise LauncherError("Lien symbolique ou jonction refusé dans le pack.")
    if not path.resolve().is_relative_to(base):
        raise LauncherError("Le chemin sort du dossier BLIXWOU.")
    return path


def validate(manifest, root: Path, *, template=False):
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("packVersion"), str) or not manifest["packVersion"]:
        raise LauncherError("Version du manifeste invalide.")
    versions = manifest.get("versions", {})
    if versions.get("minecraft") != "1.21.1" or versions.get("java") != 21:
        raise LauncherError("Le pack doit utiliser Minecraft 1.21.1 et Java 21.")
    neo = versions.get("neoforge")
    if not (template and neo is None) and not re.fullmatch(r"21\.1\.\d+(?:-beta)?", neo or ""):
        raise LauncherError("Renseignez la version exacte NeoForge 21.1.x du serveur.")
    server = manifest.get("server", {})
    if not re.fullmatch(r"[A-Za-z0-9.-]+", server.get("host", "")) or not isinstance(server.get("port"), int) or not 1 <= server["port"] <= 65535:
        raise LauncherError("Adresse du serveur invalide.")
    for name, url in manifest.get("socials", {}).items():
        if name not in ("discord", "website", "tiktok", "youtube"):
            raise LauncherError("Lien social inconnu.")
        if url:
            https_url(url)
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) > 20000:
        raise LauncherError("Liste de fichiers invalide.")
    seen = set()
    for item in files:
        path = item.get("path", "")
        safe_path(root, path)
        if path.casefold() in seen:
            raise LauncherError("Chemin dupliqué dans le manifeste.")
        seen.add(path.casefold())
        if item.get("side") not in ("client", "both", "server") or item.get("policy") not in ("enforced", "seed"):
            raise LauncherError("Côté ou politique du fichier invalide.")
        if item["policy"] == "seed" and path.split("/")[0] not in ("config", "defaultconfigs") and not (path.startswith("shaderpacks/") and path.endswith(".txt")):
            raise LauncherError("Les valeurs initiales sont réservées aux configurations.")
        if type(item.get("size")) is not int or not 0 <= item["size"] <= 8 * 1024**3:
            raise LauncherError("Taille de fichier invalide.")
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
            raise LauncherError("Empreinte SHA-256 invalide.")
        https_url(item.get("url"))
    # Reject file/directory collisions before any changes.
    for path in seen:
        if any("/".join(path.split("/")[:i]) in seen for i in range(1, len(path.split("/")))):
            raise LauncherError("Collision fichier/dossier dans le manifeste.")
    return manifest


class PackManager:
    def __init__(self, root: Path, progress=lambda s, n=0, t=0: None):
        self.root, self.game, self.progress = root, root / "game", progress
        self.state = root / "pack-state.json"
        self.tx = root / "pack-transaction"

    def recover(self):
        journal = read_json(self.tx / "journal.json")
        if not journal:
            return
        for index, op in reversed(list(enumerate(journal["operations"]))):
            active = safe_path(self.game, op["path"])
            backup = self.tx / "backup" / str(index)
            if backup.is_file():
                active.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, active)
            elif not op["existed"]:
                active.unlink(missing_ok=True)
        atomic_json(self.state, journal["oldState"])
        (self.tx / "journal.json").unlink()

    def sync(self, manifest):
        validate(manifest, self.game)
        self.recover()
        old = read_json(self.state, {"files": []})
        previous = {f["path"].casefold(): f for f in old["files"]}
        selected = [f for f in manifest["files"] if f["side"] != "server"]
        current = {f["path"].casefold(): f for f in selected}
        operations = []
        ownership = []
        for number, item in enumerate(selected, 1):
            target = safe_path(self.game, item["path"])
            self.progress("Comparaison des fichiers avec le pack GitHub", number, len(selected))
            if item["policy"] == "seed" and target.exists():
                # A seed never becomes owned merely by being present.
                if item["path"].casefold() in previous:
                    ownership.append(previous[item["path"].casefold()])
                continue
            if target.exists() and item["path"].casefold() not in previous:
                if not item['path'].startswith('shaderpacks/') or not target.is_file():
                    raise LauncherError(f"Fichier personnel déjà présent : {item['path']}. Déplacez-le avant d’installer le pack.")
                existing_hash = digest(target)
                if existing_hash != item['sha256']:
                    preserved = safe_path(self.root / 'personal-backups', item['path'] + '.' + existing_hash)
                    preserved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, preserved)
            if item["path"].casefold() in previous and previous[item["path"].casefold()]["policy"] == "seed" and target.exists():
                raise LauncherError(f"Une configuration personnelle devient imposée : {item['path']}. Déplacez-la pour confirmer cette migration.")
            ownership.append(item)
            if target.is_file() and target.stat().st_size == item["size"] and digest(target) == item["sha256"]:
                continue
            stage = self.root / "downloads" / item["sha256"]
            self.progress("Téléchargement : " + item["path"], 0, item["size"])
            download(item["url"], stage, item["sha256"], item["size"], lambda n, t, p=item["path"]: self.progress("Téléchargement : " + p, n, t))
            operations.append({"path": item["path"], "stage": str(stage), "existed": target.exists()})
        for key, item in previous.items():
            if key in current or item["policy"] == "seed":
                continue
            target = safe_path(self.game, item["path"])
            # Managed mods must match the published inventory, including removed versions.
            # Preserve modified obsolete configurations and resource packs.
            if target.is_file() and (item["path"].startswith(("mods/", "shaderpacks/")) or digest(target) == item["sha256"]):
                operations.append({"path": item["path"], "stage": None, "existed": True})
        self.tx.mkdir(parents=True, exist_ok=True)
        backup_dir = self.tx / "backup"
        backup_dir.mkdir(exist_ok=True)
        for index, op in enumerate(operations):
            backup = backup_dir / str(index)
            backup.unlink(missing_ok=True)
            if op["existed"]:
                shutil.copy2(safe_path(self.game, op["path"]), backup)
        atomic_json(self.tx / "journal.json", {"operations": operations, "oldState": old})
        try:
            for index, op in enumerate(operations, 1):
                target = safe_path(self.game, op["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                if op["stage"]:
                    prepared = self.tx / f"apply-{index}"
                    shutil.copy2(op["stage"], prepared)
                    os.replace(prepared, target)
                else:
                    target.unlink(missing_ok=True)
                self.progress("Application du pack", index, len(operations))
            atomic_json(self.state, {"packVersion": manifest["packVersion"], "files": ownership})
            (self.tx / "journal.json").unlink()  # commit point; crash beforehand rolls back
        except Exception:
            self.recover()
            raise
        for p in backup_dir.iterdir():
            if p.is_file():
                p.unlink()
        self.progress("Pack à jour", 1, 1)
        return manifest

    def fetch_and_sync(self, url):
        if not url:
            raise LauncherError("Distribution à configurer : publiez le manifeste puis renseignez manifestUrl dans launcher-config.json.")
        self.progress("Lecture du manifeste", 0, 0)
        https_url(url)
        parsed = urlsplit(url)
        parts = parsed.path.strip('/').split('/')
        if parsed.hostname == 'raw.githubusercontent.com' and len(parts) >= 4:
            owner, repository, ref = parts[:3]
            path = '/'.join(parts[3:])
            api = f'https://api.github.com/repos/{owner}/{repository}/contents/{path}?ref={quote(ref, safe="")}'
            document = get_json(api)
            if document.get('encoding') != 'base64' or not document.get('content'):
                raise LauncherError("Le manifeste GitHub est indisponible. Réessayez dans quelques instants.")
            manifest = json.loads(base64.b64decode(document['content']))
        else:
            manifest = get_json(url)
        return self.sync(manifest)
