"""Direct Minecraft Server List Ping. Timeouts/DNS are unknown, not offline."""
import json
import socket
import struct
import time


def varint(value):
    result = bytearray()
    value &= 0xffffffff
    while True:
        part = value & 127
        value >>= 7
        result.append(part | (128 if value else 0))
        if not value:
            return bytes(result)


def exact(sock, count):
    if not 0 <= count <= 2 * 1024 * 1024:
        raise ValueError("Packet too large")
    result = bytearray()
    while len(result) < count:
        data = sock.recv(count - len(result))
        if not data:
            raise ConnectionError("Closed")
        result.extend(data)
    return bytes(result)


def read_varint(sock):
    result = 0
    for index in range(5):
        part = exact(sock, 1)[0]
        result |= (part & 127) << (7 * index)
        if not part & 128:
            return result
    raise ValueError("VarInt too long")


def server_status(host, port):
    try:
        with socket.create_connection((host, port), timeout=4) as sock:
            sock.settimeout(4)
            address = host.encode("utf-8")
            # Protocol -1 requests status without asserting a game version.
            handshake = b"\x00" + varint(-1) + varint(len(address)) + address + struct.pack(">H", port) + b"\x01"
            started = time.monotonic()
            sock.sendall(varint(len(handshake)) + handshake + b"\x01\x00")
            length = read_varint(sock)
            import io
            class Buffer(io.BytesIO):
                recv = io.BytesIO.read
            packet = Buffer(exact(sock, length))
            if read_varint(packet) != 0:
                raise ValueError("Wrong packet")
            response = json.loads(exact(packet, read_varint(packet)))
            if not isinstance(response.get("version"), dict):
                raise ValueError("Invalid status")
            result = {"state": "online", "text": "En ligne"}
            players = response.get('players', {})
            if isinstance(players, dict) and all(type(players.get(k)) is int and players[k] >= 0 for k in ('online', 'max')):
                result.update(online=players['online'], max=players['max'], latency=round((time.monotonic() - started) * 1000))
            return result
    except ConnectionRefusedError:
        return {"state": "offline", "text": "Hors ligne"}
    except (OSError, ValueError, ConnectionError, UnicodeError, KeyError):
        return {"state": "unknown", "text": "Indisponible"}
