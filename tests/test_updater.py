import ctypes
from pathlib import Path
import re
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "vendor/winsparkle-tool.exe"


@pytest.mark.skipif(not TOOL.exists(), reason="Run tools/bootstrap_vendor.py for the native signature test")
def test_winsparkle_signature_rejects_modified_installer(tmp_path):
    key = tmp_path / "throwaway.key"
    installer = tmp_path / "test-installer.bin"
    installer.write_bytes(b"test release bytes; not a real executable")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    def run(*args):
        return subprocess.run([str(TOOL), *map(str, args)], capture_output=True, text=True, creationflags=flags)
    generated = run("generate-key", "--file", key)
    assert generated.returncode == 0
    public = re.search(r"Public key:\s*([A-Za-z0-9+/=]+)", generated.stdout).group(1)
    signature_output = run("sign", "--private-key-file", key, installer)
    assert signature_output.returncode == 0
    signature = re.search(r"[A-Za-z0-9+/]{86}==", signature_output.stdout).group(0)
    assert run("verify", "--public-key", public, "--signature", signature, installer).returncode == 0
    installer.write_bytes(b"tampered executable")
    assert run("verify", "--public-key", public, "--signature", signature, installer).returncode != 0
    dll = ctypes.CDLL(str(ROOT / "vendor/WinSparkle.dll"))
    dll.win_sparkle_set_eddsa_public_key.argtypes = [ctypes.c_char_p]
    dll.win_sparkle_set_eddsa_public_key.restype = ctypes.c_int
    assert dll.win_sparkle_set_eddsa_public_key(public.encode("ascii")) == 1
