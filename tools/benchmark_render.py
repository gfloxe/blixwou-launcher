"""Compare repeated background repaints with the previous rescaling behavior."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap
from blixwou.app import Landscape

app = QApplication([])
view = Landscape()
view.resize(1120, 700)
target = QPixmap(view.size())
view.render(target)
results = {}
for mode in ("rescale_every_frame", "cached"):
    start = time.perf_counter()
    for _ in range(100):
        if mode == "rescale_every_frame":
            view.scaled_size = None
        view.render(target)
    results[mode] = round((time.perf_counter() - start) * 1000, 1)
print(results)
view.close()
