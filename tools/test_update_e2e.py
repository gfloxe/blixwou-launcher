"""Opt-in updater test with a disposable signing key and localhost installer."""
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
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    import blixwou.network as network
    import blixwou.updater as updater
    from urllib.parse import urlsplit

    def local_only(url):
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password:
            raise ValueError('Only local test URLs permitted')
        return url

    network.https_url = local_only
    updater.https_url = local_only
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with tempfile.TemporaryDirectory(prefix='blixwou-update-test-') as directory:
        folder = Path(directory)
        public = folder / 'public'
        public.mkdir()
        marker = folder / 'installed.marker'
        source = folder / 'Witness.cs'
        installer = public / 'witness.exe'
        source.write_text('using System.IO; class Witness { static void Main() { File.WriteAllText(@"'
                          + str(marker).replace('"', '""') + '", "installed without clicks"); } }')

        def invoke(*cmd):
            result = subprocess.run(list(map(str, cmd)), capture_output=True, text=True,
                                    creationflags=flags, timeout=60)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return result.stdout

        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        invoke(compiler, '/nologo', '/target:winexe', '/platform:x64', '/out:' + str(installer), source)
        tool = ROOT / 'vendor/winsparkle-tool.exe'
        key = folder / 'throwaway.key'
        generated = invoke(tool, 'generate-key', '--file', key)
        public_key = re.search(r'Public key:\s*([A-Za-z0-9+/=]+)', generated).group(1)
        signature = re.search(r'[A-Za-z0-9+/]{86}==', invoke(
            tool, 'sign', '--private-key-file', key, installer)).group(0)
        original = installer.read_bytes()

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(Quiet, directory=str(public)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        ns = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
        ET.register_namespace('sparkle', ns)
        results = []
        try:
            for case, version in [('same', '1.0.0'), ('new', '1.0.1'), ('tampered', '1.0.2')]:
                marker.unlink(missing_ok=True)
                installer.write_bytes(original if case != 'tampered' else original[:-1] + bytes([original[-1] ^ 1]))
                rss = ET.Element('rss', version='2.0')
                channel = ET.SubElement(rss, 'channel')
                item = ET.SubElement(channel, 'item')
                ET.SubElement(item, '{' + ns + '}version').text = version
                ET.SubElement(item, 'enclosure', {
                    'url': base + '/witness.exe?case=' + case,
                    'length': str(installer.stat().st_size),
                    '{' + ns + '}edSignature': signature,
                })
                ET.ElementTree(rss).write(public / (case + '.xml'), encoding='utf-8', xml_declaration=True)
                info = updater.fetch_update(base + '/' + case + '.xml', '1.0.0')
                if case == 'same':
                    assert info is None
                elif case == 'new':
                    assert info and info.version == version
                    staged = updater.download_verified(folder / case, info, public_key, lambda *args: None)
                    updater.start_installer(staged)
                    deadline = time.monotonic() + 10
                    while not marker.exists() and time.monotonic() < deadline:
                        time.sleep(.1)
                    assert marker.exists(), 'Automatic installer launch was not proved'
                else:
                    assert info and info.version == version
                    try:
                        updater.download_verified(folder / case, info, public_key, lambda *args: None)
                    except updater.LauncherError:
                        pass
                    else:
                        raise AssertionError('Altered installer was accepted')
                    assert not marker.exists()
                results.append({'case': case, 'detected': info is not None, 'installed': marker.exists()})
            output = ROOT / 'output/update-e2e-results.json'
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(results, indent=2))
            print('PASS: same version ignored; new signed version installed; altered version rejected.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    run()
