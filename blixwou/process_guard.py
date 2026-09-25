"""Track the Java process across launcher crashes without confusing reused PIDs."""
import ctypes
from ctypes import wintypes
import os
from .config import LauncherError, atomic_json, read_json


def process_birth(pid):
    if os.name != "nt":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, int(pid))
    if not handle:
        if ctypes.get_last_error() == 5:
            raise LauncherError("Impossible de vérifier le processus Minecraft existant. Redémarrez Windows avant de relancer.")
        return None
    try:
        if kernel.WaitForSingleObject(handle, 0) != 258:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise LauncherError("Impossible de vérifier le processus Minecraft existant.")
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def require_game_stopped(root):
    record = read_json(root / "active-game.json")
    if record:
        birth = process_birth(record["pid"])
        if birth is not None and birth == record["birth"]:
            raise LauncherError("Minecraft BLIXWOU est déjà en cours d’exécution. Fermez le jeu avant de modifier le pack ou de le relancer.")
        (root / "active-game.json").unlink(missing_ok=True)


def record_game(root, process):
    birth = process_birth(process.pid)
    if birth is not None:
        atomic_json(root / "active-game.json", {"pid": process.pid, "birth": birth})
