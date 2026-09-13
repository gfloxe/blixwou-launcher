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

def test_updater_installs_only_after_explicit_preflight(monkeypatch):
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
    assert not any('check_update' in name for name, args in calls)
    updater.install()
    names = [name for name, args in calls]
    assert names.index('win_sparkle_set_automatic_check_for_updates') < names.index('win_sparkle_init') < names.index('win_sparkle_check_update_with_ui_and_install')
    assert dict(calls)['win_sparkle_set_automatic_check_for_updates'] == (0,)
    assert updater.can_cb() == 0
    assert dll.win_sparkle_check_update_with_ui_and_install.argtypes == []
    assert dll.win_sparkle_set_automatic_check_for_updates.argtypes == [ctypes.c_int]
    updater.close()
    assert calls[-1][0] == 'win_sparkle_cleanup'


@pytest.mark.parametrize('new,old,expected', [('0.1.10','0.1.9',True),('1.0.0','0.99.99',True),('0.1.1','0.1.1',False),('0.1.0','0.1.1',False)])
def test_numeric_versions(new, old, expected):
    from blixwou.updater import version_tuple
    assert (version_tuple(new)>version_tuple(old)) is expected


@pytest.mark.parametrize('value',['1.2','1.2.3-beta','bad','-1.2.3',None])
def test_invalid_versions(value):
    from blixwou.updater import version_tuple
    with pytest.raises(ValueError):version_tuple(value)


@pytest.mark.parametrize('body',[b'',b'not xml',b'<rss/>',b'<rss><channel><item><version>1.2.3</version></item></channel></rss>'])
def test_bad_appcast_is_silent(monkeypatch,body):
    from blixwou.updater import available_update
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):yield body
    def get(*args,**kwargs):
        assert kwargs['timeout']==5
        return Response()
    monkeypatch.setattr('blixwou.updater.request',get)
    assert available_update('https://example.org/appcast.xml','0.1.1') is None


def test_absent_appcast_is_silent(monkeypatch):
    from blixwou.updater import available_update
    import requests
    def missing(*args,**kwargs):raise requests.HTTPError('404')
    monkeypatch.setattr('blixwou.updater.request',missing)
    assert available_update('https://example.org/appcast.xml','0.1.1') is None


def test_update_failure_reactivates_launcher(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from blixwou.app import MainWindow
    from blixwou.config import load_config
    app=QApplication.instance() or QApplication([])
    window=MainWindow(tmp_path,load_config(),network=False)
    resumed=[]
    monkeypatch.setattr(window,'startup_pack',lambda:resumed.append(True))
    window.updating=True
    window.update_controls(False)
    window.start_job(lambda *args:None,lambda *args:None)
    assert window.job is None
    window.update_failed('Échec de mise à jour')
    assert window.play.isEnabled() and not window.updating
    assert resumed==[True]
    assert window.update_notice.text()=='Échec de mise à jour'
    window.update_failed('Duplicate callback')
    assert resumed==[True]
    window.close()


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
