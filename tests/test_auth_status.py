import os
import uuid
import pytest
from blixwou.auth import offline_profile, protect, minecraft_identity
from blixwou.config import LauncherError
from blixwou.status import server_status, varint, read_varint


def test_offline_identity_deterministic_separate_from_microsoft():
    profile = offline_profile("Steve")
    assert profile["id"] == "5627dd98e6be3c21b8a8e92344183641"
    assert profile["mode"] == "offline" and profile["access_token"] == "0"
    assert uuid.UUID(profile["id"]).version == 3


@pytest.mark.parametrize("name", ["a", "a b", "a/b", "a" * 17, "ééé"])
def test_offline_invalid_names(name):
    with pytest.raises(LauncherError):
        offline_profile(name)


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_dpapi_roundtrip_and_tamper_detection():
    encrypted = protect(b"test-refresh-token")
    assert b"test-refresh-token" not in encrypted
    assert protect(encrypted, decrypt=True) == b"test-refresh-token"
    with pytest.raises(LauncherError):
        protect(encrypted[:20], decrypt=True)


def test_microsoft_no_entitlement_cannot_launch(monkeypatch):
    responses = iter([
        {"Token": "xbl"}, {"Token": "xsts", "DisplayClaims": {"xui": [{"uhs": "1"}]}},
        {"access_token": "minecraft"}, {"items": []}])
    monkeypatch.setattr("blixwou.auth.api", lambda *args, **kwargs: next(responses))
    with pytest.raises(LauncherError, match="accès Minecraft Java"):
        minecraft_identity({"access_token": "oauth", "refresh_token": "refresh"})


def test_no_false_offline_on_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutError()
    monkeypatch.setattr("socket.create_connection", timeout)
    assert server_status("host", 123)["state"] == "unknown"


def test_connection_refused_is_offline(monkeypatch):
    def refused(*args, **kwargs):
        raise ConnectionRefusedError()
    monkeypatch.setattr("socket.create_connection", refused)
    assert server_status("host", 123)["state"] == "offline"


def test_real_protocol_response(monkeypatch):
    import json
    import io
    payload = json.dumps({"version": {"name": "1.21.1", "protocol": 773}, "players": {"online": 0, "max": 20}}).encode()
    packet = b"\0" + varint(len(payload)) + payload
    class Socket(io.BytesIO):
        recv = io.BytesIO.read
        def settimeout(self, timeout): pass
        def sendall(self, data): self.sent = data
    stream = Socket(varint(len(packet)) + packet)
    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: stream)
    assert server_status("host", 123)["state"] == "online"
