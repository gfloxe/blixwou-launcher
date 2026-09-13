import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from blixwou.auth import offline_profile
from blixwou.config import LauncherError, atomic_json, DEFAULT_SETTINGS
from blixwou.java import extract_java
from blixwou.minecraft import build_command
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
