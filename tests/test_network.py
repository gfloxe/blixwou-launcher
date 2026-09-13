import hashlib
import pytest
from blixwou.config import LauncherError
from blixwou.network import download, https_url


def test_download_connections_are_reused_but_isolated_between_threads():
    from blixwou.network import download_session
    from concurrent.futures import ThreadPoolExecutor
    session = download_session()
    session.cookies.set("unwanted", "cookie")
    assert download_session() is session
    assert not session.cookies
    with ThreadPoolExecutor(max_workers=1) as worker:
        other = worker.submit(download_session).result()
        assert worker.submit(download_session).result() is other
        assert other is not session
        other.close()


class Response:
    def __init__(self, data, status=200, headers=None):
        self.data, self.status_code, self.headers = data, status, headers or {}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size): yield self.data


@pytest.mark.parametrize("url", ["http://host/x", "file:///x", "https://u:p@host/x", "https:///x"])
def test_https_required(url):
    with pytest.raises(LauncherError): https_url(url)


def test_corrupt_download_never_replaces_active(tmp_path, monkeypatch):
    path = tmp_path / "active"
    path.write_bytes(b"old")
    monkeypatch.setattr("blixwou.network.request", lambda *args, **kwargs: Response(b"bad"))
    monkeypatch.setattr("blixwou.network.time.sleep", lambda n: None)
    with pytest.raises(LauncherError):
        download("https://test.invalid/file", path, hashlib.sha256(b"new").hexdigest(), 3)
    assert path.read_bytes() == b"old"


def test_interrupted_download_resumes_and_verifies(tmp_path, monkeypatch):
    path = tmp_path / "active"
    path.with_name("active.part").write_bytes(b"abc")
    def response(*args, **kwargs):
        assert kwargs["headers"]["Range"] == "bytes=3-"
        return Response(b"def", 206, {"Content-Range": "bytes 3-5/6"})
    monkeypatch.setattr("blixwou.network.request", response)
    download("https://test.invalid/file", path, hashlib.sha256(b"abcdef").hexdigest(), 6)
    assert path.read_bytes() == b"abcdef"
    assert not path.with_name("active.part").exists()


def test_server_ignores_range_restarts_safely(tmp_path, monkeypatch):
    path = tmp_path / "active"
    path.with_name("active.part").write_bytes(b"abc")
    monkeypatch.setattr("blixwou.network.request", lambda *args, **kwargs: Response(b"abcdef"))
    download("https://test.invalid/file", path, hashlib.sha256(b"abcdef").hexdigest(), 6)
    assert path.read_bytes() == b"abcdef"
