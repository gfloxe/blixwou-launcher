"""Generate a publishable manifest; every file requires explicit distribution metadata."""
import argparse
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blixwou.config import LauncherError, atomic_json
from blixwou.network import digest, https_url
from blixwou.pack import validate, safe_path


def prepare(source, metadata_file, output, release_url):
    https_url(release_url)
    if not source.is_dir() or source.is_symlink() or source.is_junction():
        raise LauncherError("Le dossier de pack est absent ou constitue un lien.")
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    manifest = {key: metadata[key] for key in ("schemaVersion", "packVersion", "versions", "server", "socials")}
    specs = metadata["fileRules"]
    files = []
    inventory = []
    for file in sorted(source.rglob("*")):
        if file.is_symlink() or file.is_junction():
            raise LauncherError("Liens interdits dans le dossier du pack.")
        if not file.is_file():
            continue
        relative = file.relative_to(source).as_posix()
        safe_path(source, relative)
        if relative not in specs:
            raise LauncherError("Métadonnées manquantes pour " + relative)
        rule = specs[relative]
        if not rule.get("redistributionAuthorized") or not rule.get("licenseOrPermission"):
            raise LauncherError("Autorisation de redistribution à documenter pour " + relative)
        sha = digest(file)
        filename = sha + "-" + file.name
        files.append({"path": relative, "url": release_url.rstrip("/") + "/" + quote(filename), "size": file.stat().st_size, "sha256": sha, "side": rule["side"], "policy": rule["policy"]})
        inventory.append((file, filename))
    if set(specs) != {f["path"] for f in files}:
        raise LauncherError("fileRules référence des fichiers absents du pack.")
    manifest["files"] = files
    validate(manifest, source)
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    for file, name in inventory:
        shutil.copy2(file, assets / name)
    atomic_json(output / "manifest.json", manifest)
    atomic_json(output / "permissions.json", specs)
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Préparer une Release de modpack BLIXWOU")
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--release-url", required=True, help="URL HTTPS réelle de téléchargement de la future Release")
    args = parser.parse_args()
    try:
        if args.output.resolve().is_relative_to(args.pack.resolve()):
            raise LauncherError("Le dossier de sortie doit se trouver hors du pack.")
        if args.output.exists() and any(args.output.iterdir()):
            raise LauncherError("Utilisez un dossier de sortie vide pour éviter des fichiers obsolètes.")
        manifest = prepare(args.pack, args.metadata, args.output, args.release_url)
        print(f"Pack {manifest['packVersion']} : {len(manifest['files'])} fichiers préparés dans {args.output.resolve()}")
        print("Les fichiers ne sont pas publiés. Téléversez les assets avant de publier le manifeste.")
    except (LauncherError, KeyError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
