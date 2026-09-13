"""Download the pinned official WinSparkle binary archive, verify before extraction."""
from pathlib import Path
import shutil
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blixwou.network import download

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/vslavik/winsparkle/releases/download/v0.9.4/WinSparkle-0.9.4.zip"
SHA256 = "6037df37fc263bd1650a1c4949681a9d40ffe991d01f35892a406cb5d103c976"

target = ROOT / "vendor" / "WinSparkle-0.9.4.zip"
download(URL, target, SHA256)
with zipfile.ZipFile(target) as archive:
    candidates = [n for n in archive.namelist() if n.lower().endswith("/x64/release/winsparkle.dll")]
    if len(candidates) != 1:
        raise RuntimeError("Structure de l’archive WinSparkle inattendue : " + repr(archive.namelist()))
    (ROOT / "vendor" / "WinSparkle.dll").write_bytes(archive.read(candidates[0]))
    for name in archive.namelist():
        base = Path(name).name
        if base.lower().startswith(("copying", "license")) or base.lower() in ("winsparkle-tool.exe", "winsparkle.h"):
            if not name.endswith("/"):
                (ROOT / "vendor" / base).write_bytes(archive.read(name))
print("WinSparkle 0.9.4 x64 vérifié et prêt.")
