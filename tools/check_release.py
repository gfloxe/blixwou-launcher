"""Fail closed for production publishing; configuration-less developer builds remain possible."""
import base64
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blixwou.config import load_config
from blixwou.network import get_json, https_url
from blixwou.pack import validate

config = load_config()
missing = []
for name, value in [("manifestUrl", config["manifestUrl"]), ("microsoft.clientId", config["microsoft"]["clientId"]), ("launcherUpdate.appcastUrl", config["launcherUpdate"]["appcastUrl"]), ("launcherUpdate.ed25519PublicKey", config["launcherUpdate"]["ed25519PublicKey"])]:
    if not value:
        missing.append(name)
if missing:
    sys.exit("Publication non prête : " + ", ".join(missing))
https_url(config["launcherUpdate"]["appcastUrl"])
if len(base64.b64decode(config["launcherUpdate"]["ed25519PublicKey"], validate=True)) != 32:
    sys.exit("Clé Ed25519 invalide.")
manifest = validate(get_json(config["manifestUrl"]), Path("output/release-validation-game"))
if config["neoforge"] and config["neoforge"] != manifest["versions"]["neoforge"]:
    sys.exit("NeoForge diffère entre configuration et manifeste.")
print("Configuration de publication vérifiée. Testez encore le parcours Microsoft et une connexion au serveur.")
