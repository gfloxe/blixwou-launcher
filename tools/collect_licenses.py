"""Preserve license notices from the installed runtime dependencies in builds."""
from importlib.metadata import distribution
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
for name in ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "minecraft-launcher-lib", "requests", "urllib3", "certifi", "idna", "charset-normalizer"):
    dist = distribution(name)
    for relative in dist.files or []:
        parts = str(relative).replace("\\", "/").split("/")
        if any(p.lower().startswith(("license", "copying")) for p in parts):
            source = Path(dist.locate_file(relative))
            if source.is_file() and source.suffix not in (".py", ".pyc"):
                folder = root / "docs" / "licenses" / name
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, folder / source.name)
python_license = Path(distribution("requests").locate_file("" )).parents[2] / "LICENSE.txt"
# Python's Windows base interpreter license, when available.
import sys
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    (root / "docs/licenses/Python").mkdir(parents=True, exist_ok=True)
    shutil.copy2(python_license, root / "docs/licenses/Python/LICENSE.txt")
print("Notices de licences collectées.")
