import json
import pytest
from blixwou.config import LauncherError, atomic_json
from tools.prepare_pack import prepare
from test_pack import manifest


def test_pack_publication_contains_real_hashes_and_explicit_sides(tmp_path):
    source = tmp_path / "pack"
    (source / "config").mkdir(parents=True)
    (source / "config/custom.json").write_text('{"enabled": true}', encoding="utf-8")
    metadata = manifest()
    metadata.pop("files")
    metadata["fileRules"] = {"config/custom.json": {"side": "both", "policy": "seed", "redistributionAuthorized": True, "licenseOrPermission": "Original configuration"}}
    spec = tmp_path / "metadata.json"
    atomic_json(spec, metadata)
    result = prepare(source, spec, tmp_path / "out", "https://test.invalid/release/tag")
    file = result["files"][0]
    assert file["size"] == 17
    assert len(file["sha256"]) == 64
    assert file["policy"] == "seed"
    assert len(list((tmp_path / "out/assets").iterdir())) == 1


def test_missing_distribution_permission_is_rejected(tmp_path):
    source = tmp_path / "pack"
    (source / "mods").mkdir(parents=True)
    (source / "mods/private.jar").write_bytes(b"private")
    metadata = manifest()
    metadata.pop("files")
    metadata["fileRules"] = {"mods/private.jar": {"side": "client", "policy": "enforced", "redistributionAuthorized": False}}
    spec = tmp_path / "metadata.json"
    atomic_json(spec, metadata)
    with pytest.raises(LauncherError, match="Autorisation"):
        prepare(source, spec, tmp_path / "out", "https://test.invalid/release/tag")
    assert not (tmp_path / "out").exists()
