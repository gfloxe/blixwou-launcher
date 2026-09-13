"""Keep one matching app-local MSVC runtime from the PySide6 wheel.

Python 3.12's older vcruntime must not shadow the newer redistributable used by Qt.
No system DLL is copied or modified.
"""
from pathlib import Path
import shutil
import sys
import PySide6

root = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "dist/BLIXWOU/_internal"
qt = Path(PySide6.__file__).parent
target.mkdir(parents=True, exist_ok=True)
for pattern in ("VCRUNTIME140*.dll", "MSVCP140*.dll", "CONCRT140.dll"):
    for file in qt.glob(pattern):
        shutil.copy2(file, target / file.name)
        print("MSVC runtime: " + file.name)

# Qt 6.11 Windows uses the OS ICU API (unversioned exports). PyInstaller can
# accidentally collect Git's ICU from PATH, whose versioned exports are incompatible.
# Let the Windows loader use the Windows ICU component, as in the source run.
for pattern in ("icuuc.dll", "icuin.dll", "icudt*.dll"):
    for file in target.glob(pattern):
        file.unlink()
        print("Excluded foreign ICU from build: " + file.name)
