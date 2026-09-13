"""Archive only source deliverables, never local profiles, test game files or keys."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
target = root / "dist" / "BLIXWOU-0.1.0-source.zip"
target.parent.mkdir(exist_ok=True)
folders = ["blixwou", "tools", "tests", "docs", "distribution", "installer", "assets", ".github"]
standalone = ["README.md", ".gitignore", "pyproject.toml", "requirements-lock.txt", "launcher-config.json", "run.py"]
files = [root / name for name in standalone]
for folder in folders:
    files.extend(p for p in (root / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
    for file in files:
        if file.suffix in (".key", ".pfx", ".pyc"):
            raise RuntimeError("Private or generated file in source list")
        z.write(file, "BLIXWOU/" + file.relative_to(root).as_posix())
print(target)
