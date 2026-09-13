"""Public desktop OAuth authorization code + PKCE; Windows user-scoped DPAPI."""
import ctypes
from ctypes import wintypes
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import time
from urllib.parse import urlsplit, parse_qs
import uuid
import webbrowser

from minecraft_launcher_lib.microsoft_account import get_secure_login_data
import requests

from .config import LauncherError, atomic_json, read_json
from .network import request
from .callback_page import callback_page

TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE = "XboxLive.signin offline_access"


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def protect(data: bytes, decrypt=False) -> bytes:
    if os.name != "nt":
        raise LauncherError("Le coffre de connexion nécessite Windows.")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    output = Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise LauncherError("Impossible d’accéder au coffre Windows. Reconnectez le compte.")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel.LocalFree(output.pbData)


def offline_profile(name):
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name):
        raise LauncherError("Le pseudo doit contenir 3 à 16 lettres, chiffres ou caractères _.")
    offline_id = uuid.UUID(bytes=hashlib.md5(("OfflinePlayer:" + name).encode()).digest(), version=3)
    return {"mode": "offline", "name": name, "id": offline_id.hex, "access_token": "0"}


def api(method, url, **kwargs):
    try:
        with request(method, url, **kwargs) as r:
            return r.json()
    except requests.HTTPError as exc:
        code = exc.response.status_code
        host = urlsplit(url).hostname
        stage = {"login.microsoftonline.com": "Microsoft OAuth", "user.auth.xboxlive.com": "Xbox Live", "xsts.auth.xboxlive.com": "Xbox XSTS", "api.minecraftservices.com": "Minecraft Services"}.get(host, "Authentification")
        try:
            details = exc.response.json()
        except ValueError:
            details = {}
        if not isinstance(details, dict):
            details = {}
        # Provider descriptions may contain personal data: extract numeric codes only.
        aad = re.search(r"AADSTS([0-9]{4,10})", str(details.get("error_description", "")))
        reason = "AADSTS" + aad[1] if aad else ""
        xerr = details.get("XErr")
        if isinstance(xerr, int):
            reason = "XErr " + str(xerr)
        suffix = f" [{stage} · HTTP {code}" + (f" · {reason}" if reason else "") + "]"
        if host == "api.minecraftservices.com" and "invalid app registration" in str(details.get("errorMessage", "")).lower():
            raise LauncherError("Minecraft refuse l’inscription de l’application BLIXWOU. Son propriétaire doit demander l’accès aux API Minecraft auprès de Microsoft : https://aka.ms/AppRegInfo . Reconnecter le compte ne résoudra pas cette autorisation." + suffix) from None
        if reason == "AADSTS7000218":
            raise LauncherError("L’application Azure est configurée comme client confidentiel. Configurez le retour localhost dans la plateforme Mobile et bureau (client public), sans secret client." + suffix) from None
        if xerr == 2148916233:
            raise LauncherError("Ce compte n’a pas encore de profil Xbox. Créez votre profil sur xbox.com puis réessayez." + suffix) from None
        if xerr == 2148916238:
            raise LauncherError("Xbox demande une autorisation familiale pour ce compte. Vérifiez les réglages avec l’organisateur de la famille." + suffix) from None
        if code == 403:
            raise LauncherError("Accès refusé par " + stage + ". L’application BLIXWOU peut nécessiter une autorisation Minecraft/Xbox de Microsoft." + suffix) from None
        if code in (400, 401):
            raise LauncherError("Connexion refusée à l’étape " + stage + ". Vérifiez la configuration de l’application et les droits du compte." + suffix) from None
        if code == 404:
            raise LauncherError("Aucun profil Minecraft Java accessible sur ce compte.") from None
        raise LauncherError("Service d’authentification indisponible. Réessayez plus tard.") from None


def minecraft_identity(oauth):
    if not oauth.get("access_token") or not oauth.get("refresh_token"):
        raise LauncherError("Microsoft n’a pas retourné de session valide. Reconnectez-vous.")
    xbl = api("POST", "https://user.auth.xboxlive.com/user/authenticate", json={
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": "d=" + oauth["access_token"]},
        "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"})
    xsts = api("POST", "https://xsts.auth.xboxlive.com/xsts/authorize", json={
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl["Token"]]},
        "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"})
    uhs = xsts["DisplayClaims"]["xui"][0]["uhs"]
    mc = api("POST", "https://api.minecraftservices.com/authentication/login_with_xbox", json={"identityToken": f"XBL3.0 x={uhs};{xsts['Token']}"})
    token = mc["access_token"]
    headers = {"Authorization": "Bearer " + token}
    entitlements = api("GET", "https://api.minecraftservices.com/entitlements/mcstore", headers=headers)
    if not any(item.get("name") in ("game_minecraft", "product_minecraft") for item in entitlements.get("items", [])):
        raise LauncherError("Ce compte ne dispose pas d’un accès Minecraft Java vérifié.")
    profile = api("GET", "https://api.minecraftservices.com/minecraft/profile", headers=headers)
    if not re.fullmatch(r"[0-9a-f]{32}", profile.get("id", "")) or not profile.get("name"):
        raise LauncherError("Profil Minecraft Java invalide.")
    return {"mode": "microsoft", "id": profile["id"], "name": profile["name"], "access_token": token, "refresh_token": oauth["refresh_token"], "xuid": xsts["DisplayClaims"]["xui"][0].get("xid", "")}


class Accounts:
    def __init__(self, root, config):
        self.root, self.config = root, config

    def selected(self):
        return read_json(self.root / "profile.json")

    def save_offline(self, name):
        profile = offline_profile(name)
        atomic_json(self.root / "profile.json", {k: profile[k] for k in ("mode", "id", "name")})
        return profile

    def save_microsoft(self, profile):
        data = protect(json.dumps({"refresh_token": profile["refresh_token"], "client_id": self.config["clientId"]}).encode())
        path = self.root / "account.dpapi"
        temp = path.with_suffix(".tmp")
        temp.write_bytes(data)
        os.replace(temp, path)
        atomic_json(self.root / "profile.json", {k: profile[k] for k in ("mode", "id", "name")})

    def logout(self):
        (self.root / "account.dpapi").unlink(missing_ok=True)
        (self.root / "profile.json").unlink(missing_ok=True)

    def login(self, progress, cancelled=lambda: False):
        client = self.config.get("clientId")
        if not client:
            raise LauncherError("Connexion Microsoft à configurer : renseignez votre application publique autorisée dans microsoft.clientId. Consultez docs/MICROSOFT.md.")
        redirect = self.config["redirectUri"]
        parsed = urlsplit(redirect)
        if parsed.scheme != "http" or parsed.hostname != "localhost" or not parsed.port or parsed.query or parsed.fragment:
            raise LauncherError("Le retour OAuth doit être une adresse HTTP localhost avec port explicite.")
        url, state, verifier = get_secure_login_data(client, redirect)
        # Always offer existing accounts and "Use another account" in Microsoft's UI.
        url += "&prompt=select_account"
        result = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # Authorization code and state must never enter logs.

            def do_GET(self):
                request_path = urlsplit(self.path)
                values = parse_qs(request_path.query)
                valid = request_path.path == parsed.path and hmac.compare_digest(values.get("state", [""])[0], state)
                valid = valid and len(values.get("state", [])) == 1 and ((len(values.get("code", [])) == 1) != (len(values.get("error", [])) == 1))
                if valid and not result:
                    result.update(values)
                page = callback_page("cancelled" if valid and "error" in values else "received" if valid else "invalid")
                self.send_response(200 if valid else 400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(page)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Browser closure must not discard an accepted authorization code.

        try:
            server = HTTPServer(("127.0.0.1", parsed.port), Handler)
        except OSError:
            raise LauncherError("Le port de retour Microsoft est occupé. Fermez l’autre tentative de connexion.") from None
        with server:
            server.timeout = 0.5
            progress("Connectez-vous dans votre navigateur", 0, 0)
            if not webbrowser.open(url):
                raise LauncherError("Impossible d’ouvrir le navigateur par défaut.")
            deadline = time.monotonic() + 180
            while not result and time.monotonic() < deadline and not cancelled():
                server.handle_request()
        if not result.get("code"):
            if result.get("error"):
                raise LauncherError("La connexion a été annulée ou refusée dans le navigateur Microsoft. Relancez-la depuis le profil.")
            raise LauncherError("Connexion Microsoft annulée ou délai de trois minutes dépassé.")
        progress("Vérification de l’accès Minecraft Java", 0, 0)
        oauth = api("POST", TOKEN_URL, data={"client_id": client, "scope": SCOPE, "code": result["code"][0], "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
        profile = minecraft_identity(oauth)
        profile["client_id"] = client
        self.save_microsoft(profile)
        return profile

    def for_launch(self):
        profile = self.selected()
        if not profile:
            raise LauncherError("Choisissez un profil avant de jouer.")
        if profile["mode"] == "offline":
            return offline_profile(profile["name"])
        try:
            secret = json.loads(protect((self.root / "account.dpapi").read_bytes(), decrypt=True))
        except (OSError, ValueError):
            raise LauncherError("Session Microsoft absente. Reconnectez-vous.") from None
        if secret["client_id"] != self.config["clientId"]:
            raise LauncherError("L’application Microsoft a changé. Reconnectez-vous.")
        oauth = api("POST", TOKEN_URL, data={"client_id": self.config["clientId"], "scope": SCOPE, "refresh_token": secret["refresh_token"], "grant_type": "refresh_token"})
        # Persist rotated refresh token even if Xbox/Minecraft is temporarily down.
        if oauth.get("refresh_token"):
            temp = self.root / "account.tmp"
            temp.write_bytes(protect(json.dumps({"refresh_token": oauth["refresh_token"], "client_id": self.config["clientId"]}).encode()))
            os.replace(temp, self.root / "account.dpapi")
        profile = minecraft_identity(oauth)
        profile["client_id"] = self.config["clientId"]
        self.save_microsoft(profile)
        return profile
