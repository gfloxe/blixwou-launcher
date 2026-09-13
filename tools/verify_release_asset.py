"""Verify the actual published installer before advancing the stable appcast."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blixwou.config import load_config
from blixwou.network import request, digest
from blixwou.updater import version_tuple

parser=argparse.ArgumentParser()
parser.add_argument('--version',required=True)
parser.add_argument('--installer',type=Path,required=True)
parser.add_argument('--appcast',type=Path,required=True)
args=parser.parse_args()
ns='{http://www.andymatuschak.org/xml-namespaces/sparkle}'
root=ET.parse(args.appcast).getroot()
assert root.findtext('./channel/item/'+ns+'version')==args.version
existing=Path('appcast.xml')
if existing.exists():
    old=ET.parse(existing).findtext('./channel/item/'+ns+'version')
    assert version_tuple(old)<=version_tuple(args.version),'Appcast downgrade refused'
entry=root.find('./channel/item/enclosure')
expected=f'https://github.com/gfloxe/blixwou-launcher/releases/download/v{args.version}/BLIXWOU-Setup-{args.version}-x64.exe'
assert entry.attrib['url']==expected
size=args.installer.stat().st_size
assert int(entry.attrib['length'])==size
received=0
checksum=hashlib.sha256()
with request('GET',expected,stream=True) as response:
    for chunk in response.iter_content(262144):
        received+=len(chunk)
        assert received<=size,'Remote installer larger than expected'
        checksum.update(chunk)
assert received==size and checksum.hexdigest()==digest(args.installer),'Remote installer differs'
result=subprocess.run(['vendor/winsparkle-tool.exe','verify','--public-key',load_config()['launcherUpdate']['ed25519PublicKey'],
    '--signature',entry.attrib[ns+'edSignature'],str(args.installer)],capture_output=True,text=True)
assert result.returncode==0,'Invalid Ed25519 signature'
print('Installateur GitHub identique ; signature valide ; appcast prêt à publier.')
