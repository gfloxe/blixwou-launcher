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

def test_updater_checks_silently_after_init(monkeypatch):
    from blixwou.updater import LauncherUpdater
    import json
    calls = []
    class Function:
        def __init__(self, name): self.name = name
        def __call__(self, *args):
            calls.append((self.name, args))
            return 1
    class DLL:
        def __getattr__(self, name):
            fn = Function(name)
            setattr(self, name, fn)
            return fn
    dll = DLL()
    monkeypatch.setattr(ctypes, 'CDLL', lambda path: dll)
    config = json.loads((ROOT / 'launcher-config.json').read_text())
    updater = LauncherUpdater(config['launcherUpdate'], config['appVersion'], lambda: False, lambda: None)
    names = [name for name, args in calls]
    assert names.index('win_sparkle_set_automatic_check_for_updates') < names.index('win_sparkle_init') < names.index('win_sparkle_check_update_without_ui')
    assert dict(calls)['win_sparkle_set_automatic_check_for_updates'] == (1,)
    assert updater.can_cb() == 0
    assert dll.win_sparkle_check_update_without_ui.argtypes == []
    assert dll.win_sparkle_set_automatic_check_for_updates.argtypes == [ctypes.c_int]
    updater.close()
    assert calls[-1][0] == 'win_sparkle_cleanup'


def test_versions_share_config_source(monkeypatch, tmp_path):
    import json, tomllib
    from blixwou import minecraft
    config = json.loads((ROOT / 'launcher-config.json').read_text())
    assert tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version'] == config['appVersion']
    captured = {}
    def command(version, folder, options):
        captured.update(options)
        return []
    monkeypatch.setattr(minecraft.command, 'get_minecraft_command', command)
    monkeypatch.setattr(minecraft, 'load_config', lambda: {'appVersion': '9.8.7'})
    minecraft.build_command(tmp_path, 'test', 'java', {'ramMb':4096,'width':1280,'height':720}, {'name':'Test','id':'0','access_token':'0','mode':'offline'}, {})
    assert captured['launcherVersion'] == '9.8.7'
    build = (ROOT / 'tools/build_windows.ps1').read_text()
    assert '/DAppVersion=$version' in build
    assert '#define AppVersion' not in (ROOT / 'installer/BLIXWOU.iss').read_text()
