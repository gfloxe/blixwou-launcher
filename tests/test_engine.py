import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from blixwou.auth import offline_profile
from blixwou.config import LauncherError, atomic_json, DEFAULT_SETTINGS
from blixwou.java import extract_java
from blixwou.minecraft import build_command, prepare_minecraft
from blixwou.minecraft import ready_game_title
from blixwou.process_guard import process_birth, record_game, require_game_stopped


def test_arguments_use_dedicated_folder_offline_identity_and_quickplay(tmp_path):
    version = "neoforge-test"
    metadata = {"id": version, "type": "release", "mainClass": "example.Main", "assets": "27", "libraries": [], "arguments": {
        "jvm": ["-cp", "${classpath}"],
        "game": ["--username", "${auth_player_name}", "--uuid", "${auth_uuid}", "--accessToken", "${auth_access_token}", "--userType", "${user_type}", "--gameDir", "${game_directory}", "--clientId", "${clientid}", "--xuid", "${auth_xuid}",
            {"rules": [{"action": "allow", "features": {"is_quick_play_multiplayer": True}}], "value": ["--quickPlayMultiplayer", "${quickPlayMultiplayer}"]}]}}
    atomic_json(tmp_path / "minecraft/versions" / version / (version + ".json"), metadata)
    args = build_command(tmp_path, version, "C:/Java 21/bin/java.exe", DEFAULT_SETTINGS, offline_profile("Steve"), {"host": "BLIXWOU.exaroton.me", "port": 48255})
    assert args[0] == "C:/Java 21/bin/java.exe"
    assert "-Xmx4096M" in args
    assert "-Xms4096M" in args
    assert "-XX:+UseG1GC" in args
    assert args[args.index("--gameDir") + 1] == str(tmp_path / "game")
    assert "--quickPlayMultiplayer" not in args
    assert "--server" not in args
    assert args[args.index("--userType") + 1] == "legacy"
    assert args[args.index("--accessToken") + 1] == "0"
    assert not any("${" in a for a in args)


def test_java_archive_traversal_rejected(tmp_path):
    import zipfile
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../outside.txt", "bad")
    with pytest.raises(LauncherError):
        extract_java(archive, tmp_path / "runtime")
    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows process handles")
def test_running_game_survives_launcher_restart_guard(tmp_path):
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert process_birth(process.pid)
        record_game(tmp_path, process)
        with pytest.raises(LauncherError):
            require_game_stopped(tmp_path)
    finally:
        process.terminate()
        process.wait(timeout=10)
    require_game_stopped(tmp_path)
    assert not (tmp_path / "active-game.json").exists()

@pytest.mark.parametrize('stopped', [True, False])
def test_game_exit_distinguishes_stop_from_crash(tmp_path, monkeypatch, stopped):
    from blixwou.minecraft import launch_game, GameSession
    class Process:
        stdout = []
        def wait(self): return 1
    process = Process()
    session = GameSession()
    monkeypatch.setattr('blixwou.minecraft.subprocess.Popen', lambda *a, **k: process)
    monkeypatch.setattr('blixwou.minecraft.record_game', lambda *a: None)
    (tmp_path / 'logs').mkdir()
    def progress(step, *args):
        if step == 'Minecraft est lancé':
            assert session.process is process
            session.stopping = stopped
    if stopped:
        assert launch_game(tmp_path, [], {}, progress, session) == 1
    else:
        with pytest.raises(LauncherError):
            launch_game(tmp_path, [], {}, progress, session)
    assert session.process is None


def test_neoforge_loading_window_is_not_considered_ready():
    assert not ready_game_title('Minecraft: NeoForge Loading...')
    assert not ready_game_title('Minecraft : Chargement')
    assert not ready_game_title('Java Platform SE binary')
    assert ready_game_title('Minecraft NeoForge* 1.21.1')


def test_published_neoforge_installer_is_accepted_when_versions_api_omits_it(tmp_path, monkeypatch):
    import blixwou.minecraft as minecraft

    neo = '21.1.250'
    engine = tmp_path / 'minecraft'
    installed_file = engine / 'versions' / ('neoforge-' + neo) / 'marker.bin'
    installed_file.parent.mkdir(parents=True)
    installed_file.write_bytes(b'installed')
    atomic_json(tmp_path / 'neoforge-installed.json', {
        'version': neo, 'files': {installed_file.relative_to(engine).as_posix(): 'expected'}
    })
    def official_manifest(url):
        assert url == minecraft.MOJANG_MANIFEST
        return {'versions': [{'id': '1.21.1', 'url': 'https://example.com/1.21.1.json', 'sha1': 'a' * 40}]}
    def fake_download(url, target, *args, **kwargs):
        if str(target).endswith('1.21.1.json'):
            atomic_json(target, {'javaVersion': {'majorVersion': 21}, 'libraries': [],
                                 'downloads': {'client': {'url': 'https://example.com/client.jar', 'sha1': 'b' * 40, 'size': 1}}})
    monkeypatch.setattr(minecraft, 'get_json', official_manifest)
    monkeypatch.setattr(minecraft, 'neoforge_installer', lambda version: ('https://example.com/installer.jar', 'c' * 64))
    monkeypatch.setattr(minecraft, 'ensure_java', lambda *args: 'java')
    monkeypatch.setattr(minecraft, 'download', fake_download)
    monkeypatch.setattr(minecraft, 'digest', lambda path: 'expected')
    monkeypatch.setattr(minecraft.install, 'install_libraries', lambda *args, **kwargs: None)
    monkeypatch.setattr(minecraft.install, 'install_assets', lambda *args, **kwargs: None)

    manifest = {'versions': {'minecraft': '1.21.1', 'neoforge': neo, 'java': 21}}
    assert prepare_minecraft(tmp_path, manifest, DEFAULT_SETTINGS, lambda *args: None) == ('java', 'neoforge-' + neo)
