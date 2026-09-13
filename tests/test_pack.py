import copy
import hashlib
import json
from pathlib import Path
import pytest
from blixwou.config import LauncherError, atomic_json, read_json
from blixwou.pack import PackManager, safe_path, validate


def manifest(files=None):
    return {"schemaVersion": 1, "packVersion": "1", "versions": {"minecraft": "1.21.1", "neoforge": "21.1.250", "java": 21}, "server": {"host": "BLIXWOU.exaroton.me", "port": 48255}, "socials": {}, "files": files or []}


def item(path, content=b"data", policy="enforced", side="client"):
    return {"path": path, "url": "https://test.invalid/" + path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(), "policy": policy, "side": side}


@pytest.mark.parametrize("path", ["../escape", "/mods/a", "mods/../x", "mods/CON.jar", "mods/a:stream", "mods//a", "mods/a.", "mods/a ", "mods\\a.jar", "screenshots/x.png", "saves/world", "options.txt", "mods/nul/x", "mods/a\x00b"])
def test_windows_unsafe_paths(path, tmp_path):
    with pytest.raises(LauncherError):
        safe_path(tmp_path, path)


def test_wrong_versions_and_case_collision(tmp_path):
    data = manifest([item("mods/A.jar"), item("mods/a.jar")])
    with pytest.raises(LauncherError):
        validate(data, tmp_path)
    for key, value in [("minecraft", "1.21.10"), ("java", 17), ("neoforge", None), ("neoforge", "21.10.64")]:
        data = manifest()
        data["versions"][key] = value
        with pytest.raises(LauncherError):
            validate(data, tmp_path)


@pytest.fixture
def downloads(monkeypatch):
    calls = []
    def fake(url, path, sha, size, progress):
        calls.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
    monkeypatch.setattr("blixwou.pack.download", fake)
    return calls


def test_differential_updates_and_corruption_repair(tmp_path, downloads):
    manager = PackManager(tmp_path)
    data = manifest([item("mods/a.jar")])
    manager.sync(data)
    manager.sync(data)
    assert len(downloads) == 1
    (tmp_path / "game/mods/a.jar").write_bytes(b"bad!")
    manager.sync(data)
    assert len(downloads) == 2
    assert (tmp_path / "game/mods/a.jar").read_bytes() == b"data"


def test_seed_personal_and_server_files_preserved(tmp_path, downloads):
    game = tmp_path / "game"
    (game / "config").mkdir(parents=True)
    (game / "config/player.json").write_bytes(b"personal")
    data = manifest([item("config/player.json", policy="seed"), item("mods/server.jar", side="server"), item("mods/client.jar")])
    manager = PackManager(tmp_path)
    manager.sync(data)
    assert len(downloads) == 1
    assert not (game / "mods/server.jar").exists()
    assert (game / "config/player.json").read_bytes() == b"personal"
    (game / "mods/personal.jar").write_bytes(b"mine")
    manager.sync(manifest())
    assert not (game / "mods/client.jar").exists()
    assert (game / "mods/personal.jar").read_bytes() == b"mine"
    assert (game / "config/player.json").read_bytes() == b"personal"


def test_unmanaged_conflict_is_not_overwritten(tmp_path, downloads):
    path = tmp_path / "game/mods/a.jar"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"personal")
    with pytest.raises(LauncherError):
        PackManager(tmp_path).sync(manifest([item("mods/a.jar")]))
    assert path.read_bytes() == b"personal"
    assert not downloads


def test_identical_unmanaged_mod_is_adopted(tmp_path, downloads):
    path = tmp_path / "game/mods/a.jar"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"data")
    manager = PackManager(tmp_path)
    manager.sync(manifest([item("mods/a.jar")]))
    assert read_json(manager.state)["files"] == [item("mods/a.jar")]
    assert not downloads
    assert path.read_bytes() == b"data"


def test_orphan_mod_reported_without_changes(tmp_path, downloads, caplog):
    path = tmp_path / "game/mods/old.jar"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"personal")
    reports = []
    PackManager(tmp_path, lambda text, *args: reports.append(text)).sync(manifest([item("mods/a.jar")]))
    assert path.read_bytes() == b"personal"
    assert "Mod hors pack conservé : mods/old.jar" in caplog.text
    assert "Mods hors pack : mods/old.jar" in reports


def test_download_failure_changes_no_active_files(tmp_path, downloads, monkeypatch):
    manager = PackManager(tmp_path)
    manager.sync(manifest([item("mods/a.jar")]))
    def fail(*args, **kwargs):
        raise LauncherError("network")
    monkeypatch.setattr("blixwou.pack.download", fail)
    with pytest.raises(LauncherError):
        manager.sync(manifest([item("mods/b.jar")]))
    assert (tmp_path / "game/mods/a.jar").read_bytes() == b"data"
    assert read_json(manager.state)["files"][0]["path"] == "mods/a.jar"


def test_crash_recovery_restores_owned_file_and_state(tmp_path):
    manager = PackManager(tmp_path)
    path = tmp_path / "game/mods/a.jar"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"new")
    backup = manager.tx / "backup/0"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"old")
    old_state = {"packVersion": "1", "files": [item("mods/a.jar", b"old")]}
    atomic_json(manager.tx / "journal.json", {"oldState": old_state, "operations": [{"path": "mods/a.jar", "existed": True}]})
    manager.recover()
    assert path.read_bytes() == b"old"
    assert read_json(manager.state) == old_state
    assert not (manager.tx / "journal.json").exists()


def test_apply_failure_rolls_back_entire_transaction(tmp_path, downloads, monkeypatch):
    import blixwou.pack as pack
    manager = PackManager(tmp_path)
    manager.sync(manifest([item("mods/a.jar")]))
    real_replace = pack.os.replace
    def fail(source, target):
        if str(target).endswith("b.jar"):
            raise OSError("locked")
        return real_replace(source, target)
    monkeypatch.setattr(pack.os, "replace", fail)
    with pytest.raises(OSError):
        manager.sync(manifest([item("mods/b.jar")]))
    assert (tmp_path / "game/mods/a.jar").read_bytes() == b"data"
    assert not (tmp_path / "game/mods/b.jar").exists()


def test_modified_obsolete_managed_mod_is_removed(tmp_path, downloads):
    manager = PackManager(tmp_path)
    manager.sync(manifest([item("mods/a.jar")]))
    path = tmp_path / "game/mods/a.jar"
    path.write_bytes(b"modified")
    manager.sync(manifest())
    assert not path.exists()


def test_identical_content_at_two_paths(tmp_path, downloads):
    PackManager(tmp_path).sync(manifest([item("config/a.json"), item("config/b.json")]))
    assert (tmp_path / "game/config/a.json").read_bytes() == b"data"
    assert (tmp_path / "game/config/b.json").read_bytes() == b"data"


def test_mod_rename_removes_modified_old_version(tmp_path, downloads):
    manager = PackManager(tmp_path)
    manager.sync(manifest([item("mods/old.jar")]))
    (tmp_path / "game/mods/old.jar").write_bytes(b"edit")
    manager.sync(manifest([item("mods/new.jar")]))
    assert not (tmp_path / "game/mods/old.jar").exists()
    assert (tmp_path / "game/mods/new.jar").read_bytes() == b"data"


def test_modified_obsolete_config_still_preserved(tmp_path, downloads):
    manager = PackManager(tmp_path)
    manager.sync(manifest([item("config/old.json")]))
    path = tmp_path / "game/config/old.json"
    path.write_bytes(b"personal")
    manager.sync(manifest())
    assert path.read_bytes() == b"personal"


def test_shaders_repair_remove_and_preserve_player_settings(tmp_path, downloads):
    manager = PackManager(tmp_path)
    data = manifest([item("shaderpacks/a.zip"), item("shaderpacks/a.zip.txt", policy="seed")])
    manager.sync(data)
    archive = tmp_path / "game/shaderpacks/a.zip"
    settings = tmp_path / "game/shaderpacks/a.zip.txt"
    archive.write_bytes(b"edit")
    settings.write_bytes(b"my settings")
    manager.sync(data)
    assert archive.read_bytes() == b"data"
    assert settings.read_bytes() == b"my settings"
    manager.sync(manifest())
    assert not archive.exists()
    assert settings.read_bytes() == b"my settings"

def test_github_manifest_uses_current_api_content(tmp_path, monkeypatch):
    import base64
    calls = []
    current = manifest()
    def fetch(url):
        calls.append(url)
        return {'encoding': 'base64', 'content': base64.b64encode(json.dumps(current).encode()).decode()}
    monkeypatch.setattr('blixwou.pack.get_json', fetch)
    manager = PackManager(tmp_path, lambda *args: None)
    monkeypatch.setattr(manager, 'sync', lambda data: data)
    assert manager.fetch_and_sync('https://raw.githubusercontent.com/gfloxe/BLIXWOU/main/manifest.json') == current
    assert calls == ['https://api.github.com/repos/gfloxe/BLIXWOU/contents/manifest.json?ref=main']

@pytest.mark.parametrize('content', [b'data', b'personal'])
def test_adopt_existing_shader_preserves_different_content(tmp_path, downloads, content):
    target = tmp_path / 'game/shaderpacks/example.zip'
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    manager = PackManager(tmp_path)
    manager.sync(manifest([item('shaderpacks/example.zip')]))
    assert target.read_bytes() == b'data'
    assert read_json(manager.state)['files'][0]['path'] == 'shaderpacks/example.zip'
    backups = list((tmp_path / 'personal-backups').rglob('*'))
    if content != b'data':
        assert any(p.is_file() and p.read_bytes() == content for p in backups)
    else:
        assert not downloads and not backups
