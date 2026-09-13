"""Build WinSparkle RSS from an installer and its signature (no private key needed)."""
import argparse
import base64
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blixwou.network import https_url

parser = argparse.ArgumentParser()
parser.add_argument("--installer", required=True, type=Path)
parser.add_argument("--version", required=True)
parser.add_argument("--url", required=True)
parser.add_argument("--signature", required=True, help="Signature EdDSA générée par winsparkle-tool sign")
parser.add_argument("--output", type=Path, default=Path("appcast.xml"))
args = parser.parse_args()
https_url(args.url)
if len(base64.b64decode(args.signature, validate=True)) != 64:
    parser.error("Signature Ed25519 invalide")
namespace = "http://www.andymatuschak.org/xml-namespaces/sparkle"
ET.register_namespace("sparkle", namespace)
rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "BLIXWOU"
ET.SubElement(channel, "language").text = "fr"
item = ET.SubElement(channel, "item")
ET.SubElement(item, "title").text = "BLIXWOU " + args.version
ET.SubElement(item, "pubDate").text = format_datetime(datetime.now(timezone.utc))
ET.SubElement(item, "{" + namespace + "}version").text = args.version
ET.SubElement(item, "{" + namespace + "}minimumSystemVersion").text = "10.0.17763"
ET.SubElement(item, "enclosure", {"url": args.url, "length": str(args.installer.stat().st_size), "type": "application/octet-stream", "{" + namespace + "}edSignature": args.signature, "{" + namespace + "}os": "windows-x64", "{" + namespace + "}installerArguments": "/SILENT /SP- /NOICONS"})
ET.indent(rss)
ET.ElementTree(rss).write(args.output, encoding="utf-8", xml_declaration=True)
print(args.output.resolve())
