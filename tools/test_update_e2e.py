"""Opt-in native WinSparkle test, isolated identity, localhost and disposable key."""
import argparse
import base64
import functools
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def child(args):
    import blixwou.network as network
    import blixwou.updater as updater
    from urllib.parse import urlsplit
    # This opt-in harness is the only HTTP exception; production stays HTTPS.
    def loopback(url):
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password:
            raise ValueError('Only local test URLs permitted')
        return url
    network.https_url = loopback
    updater.https_url = loopback
    available = updater.available_update(args.url, '1.0.0')
    if available is None:
        print(json.dumps({'case':args.case,'update':False,'marker':Path(args.marker).exists()}),flush=True)
        return
    events=[]
    engine=updater.LauncherUpdater({'appcastUrl':args.url,'ed25519PublicKey':args.public},'1.0.0',
        lambda:True,lambda:events.append('shutdown'),lambda:events.append('error'),lambda:events.append('cancelled'),
        identity=(args.identity,'Native test'))
    engine.install()
    deadline=time.monotonic()+30
    while time.monotonic()<deadline and not Path(args.marker).exists() and 'error' not in events:
        time.sleep(.1)
    # Allow a failed signature time to prove no installer was launched.
    if 'error' in events:time.sleep(1)
    result={'case':args.case,'update':True,'events':events,'marker':Path(args.marker).exists()}
    print(json.dumps(result),flush=True)
    engine.close()


def cleanup_registry(identity):
    import winreg
    assert identity.startswith('BLIXWOU-Update-Test-') and len(identity)==len('BLIXWOU-Update-Test-')+32
    def remove(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_READ|winreg.KEY_WRITE) as key:
                children=[]
                i=0
                while True:
                    try:children.append(winreg.EnumKey(key,i));i+=1
                    except OSError:break
            for name in children:remove(path+'\\'+name)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
        except FileNotFoundError:pass
    remove('Software\\'+identity)


def run():
    import winreg
    identity='BLIXWOU-Update-Test-'+uuid4().hex
    registry='Software\\'+identity
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,registry):
            raise RuntimeError('Test registry identity already exists')
    except FileNotFoundError:pass
    flags=subprocess.CREATE_NO_WINDOW
    with tempfile.TemporaryDirectory(prefix='blixwou-update-test-') as temp:
        temp=Path(temp); public_dir=temp/'public'; public_dir.mkdir()
        key=temp/'throwaway.key'; marker=temp/'installed.marker'
        source=temp/'Witness.cs'; installer=public_dir/'witness.exe'
        source.write_text('using System.IO; class Witness { static void Main() { File.WriteAllText(@"'+str(marker).replace('"','""')+'", "installed without clicks"); } }')
        def invoke(*cmd):
            result=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,creationflags=flags,timeout=60)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
            return result.stdout
        invoke(Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe','/nologo','/target:winexe','/platform:x64','/out:'+str(installer),source)
        tool=ROOT/'vendor/winsparkle-tool.exe'
        generated=invoke(tool,'generate-key','--file',key)
        public=re.search(r'Public key:\s*([A-Za-z0-9+/=]+)',generated).group(1)
        signature=re.search(r'[A-Za-z0-9+/]{86}==',invoke(tool,'sign','--private-key-file',key,installer)).group(0)
        invoke(tool,'verify','--public-key',public,'--signature',signature,installer)
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(public_dir)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        ns='http://www.andymatuschak.org/xml-namespaces/sparkle'
        ET.register_namespace('sparkle',ns)
        results=[]
        try:
            for case,version in [('same','1.0.0'),('new','1.0.1'),('tampered','1.0.2')]:
                marker.unlink(missing_ok=True)
                if case=='tampered':
                    with installer.open('ab') as stream:stream.write(b'unsigned modification')
                rss=ET.Element('rss',version='2.0');channel=ET.SubElement(rss,'channel')
                ET.SubElement(channel,'title').text='BLIXWOU isolated native test'
                item=ET.SubElement(channel,'item');ET.SubElement(item,'title').text=version
                ET.SubElement(item,'{'+ns+'}version').text=version
                ET.SubElement(item,'enclosure',{'url':base+'/witness.exe?case='+case,'length':str(installer.stat().st_size),
                    'type':'application/octet-stream','{'+ns+'}edSignature':signature,'{'+ns+'}installerArguments':'/SILENT /SP- /NOICONS'})
                ET.ElementTree(rss).write(public_dir/(case+'.xml'),encoding='utf-8',xml_declaration=True)
                completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child','--case',case,
                    '--url',base+'/'+case+'.xml','--identity',identity,'--public',public,'--marker',str(marker)],
                    capture_output=True,text=True,creationflags=flags,timeout=45)
                print(completed.stdout,flush=True)
                if completed.returncode:raise RuntimeError(completed.stderr)
                result=json.loads(completed.stdout.strip().splitlines()[-1]);results.append(result)
                if case=='same':assert not result['update'] and not result['marker']
                elif case=='new':assert result['marker'], 'No witness: automatic installation was not proved'
                else:assert not result['marker'] and 'error' in result['events'], 'Invalid signature was not rejected'
            (ROOT/'output/update-e2e-results.json').write_text(json.dumps(results,indent=2))
            print('PASS: same version ignored; new version installed without clicks; altered signature rejected.',flush=True)
        finally:
            server.shutdown();server.server_close();thread.join()
            cleanup_registry(identity)
            print('Only test registry identity removed: '+registry,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--child',action='store_true')
    for name in ('case','url','identity','public','marker'):parser.add_argument('--'+name)
    args=parser.parse_args()
    if args.child:child(args)
    else:run()
