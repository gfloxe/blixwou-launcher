"""Real isolated installation test, without launching Minecraft or changing production config."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blixwou.minecraft import prepare_minecraft, build_command
from blixwou.config import DEFAULT_SETTINGS, atomic_json
from blixwou.auth import offline_profile

parser = argparse.ArgumentParser()
parser.add_argument("--neoforge", required=True)
parser.add_argument("--java", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1] / "output/integration-install"
root.mkdir(parents=True, exist_ok=True)
manifest = {"versions": {"minecraft": "1.21.1", "neoforge": args.neoforge, "java": 21}}
settings = DEFAULT_SETTINGS | {"javaPath": args.java}
last = [""]
def progress(step, n=0, t=0):
    if step != last[0]:
        print(step, flush=True)
        last[0] = step
java, version = prepare_minecraft(root, manifest, settings, progress)
command = build_command(root, version, java, settings, offline_profile("BlixTest"), {"host": "BLIXWOU.exaroton.me", "port": 48255})
assert "--quickPlayMultiplayer" in command
assert not any("${" in arg for arg in command)
atomic_json(root / "result.json", {"installationSucceeded": True, "minecraft": "1.21.1", "testNeoforge": args.neoforge, "validCommandGenerated": True, "gameLaunched": False, "productionConfigChanged": False})
print("Installation isolée vérifiée ; jeu non lancé et configuration du serveur inchangée.")
