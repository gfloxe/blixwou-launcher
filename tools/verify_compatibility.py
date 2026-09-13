"""Read-only official source check; never selects a NeoForge build for the server."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blixwou.network import get_json
from blixwou.minecraft import MOJANG_MANIFEST, NEOFORGE_VERSIONS
from blixwou.java import ADOPTIUM

catalogue = get_json(MOJANG_MANIFEST)
item = next(v for v in catalogue["versions"] if v["id"] == "1.21.1")
metadata = get_json(item["url"])
neoforge = [v for v in get_json(NEOFORGE_VERSIONS)["versions"] if v.startswith("21.1.")]
java = get_json(ADOPTIUM)[0]
report = {
    "minecraft": metadata["id"],
    "javaMajorFromMojang": metadata["javaVersion"]["majorVersion"],
    "minecraftMetadata": item["url"],
    "minecraftMetadataSha1": item["sha1"],
    "quickPlayMultiplayerSupported": any(isinstance(a, dict) and "is_quick_play_multiplayer" in str(a) for a in metadata["arguments"]["game"]),
    "neoforgeAvailableFor1211": len(neoforge),
    "serverNeoforgeSelection": None,
    "javaDistribution": java["release_name"],
    "javaArchitecture": java["binary"]["architecture"],
    "javaDownload": java["binary"]["package"]["link"],
    "javaSha256": java["binary"]["package"]["checksum"],
}
print(json.dumps(report, indent=2))
if len(sys.argv) == 2:
    Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
