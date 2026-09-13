"""Optional real downloads: verify Java and NeoForge metadata without selecting server NeoForge."""
import json
from pathlib import Path
import re
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blixwou.java import ensure_java
from blixwou.minecraft import NEOFORGE_VERSIONS
from blixwou.network import get_json, request, download

root = Path(__file__).resolve().parents[1] / "output/integration-probe"
root.mkdir(parents=True, exist_ok=True)
java = ensure_java(root, "", lambda step, n=0, t=0: None)
versions = [v for v in get_json(NEOFORGE_VERSIONS)["versions"] if re.fullmatch(r"21\.1\.\d+", v)]
probe = "21.1.250"
assert probe in versions
url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{probe}/neoforge-{probe}-installer.jar"
with request("GET", url + ".sha256") as response:
    checksum = response.text.strip()
jar = root / ("probe-" + probe + ".jar")
download(url, jar, checksum)
with zipfile.ZipFile(jar) as z:
    profile = json.loads(z.read("install_profile.json"))
    assert profile["minecraft"] == "1.21.1"
print(json.dumps({"java21x64ExecutedSuccessfully": True, "javaExecutable": java, "neoforgeInstallerMetadataProbe": probe, "probeMinecraftTarget": profile["minecraft"], "note": "Validation d’un artefact officiel uniquement ; aucune sélection ni installation NeoForge pour le serveur."}, indent=2))
