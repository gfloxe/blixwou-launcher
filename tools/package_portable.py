"""Package the onedir build for users who prefer no installer."""
import hashlib
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
folder = root / "dist/BLIXWOU"
target = root / "dist/BLIXWOU-0.1.0-portable-x64.zip"
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for file in folder.rglob("*"):
        if file.is_file():
            z.write(file, "BLIXWOU/" + file.relative_to(folder).as_posix())
print(target)
artifacts = [root / "dist/BLIXWOU-0.1.0-source.zip", target, root / "dist/installer/BLIXWOU-Setup-0.1.0-x64.exe"]
lines = []
for artifact in artifacts:
    with artifact.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    lines.append(sha + "  " + artifact.relative_to(root / "dist").as_posix())
(root / "dist/SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
