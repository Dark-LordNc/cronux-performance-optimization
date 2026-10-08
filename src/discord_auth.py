"""Connexion « Se connecter avec Discord » (OAuth2 officiel).

Ce que la connexion OAuth donne : ton identité (pseudo, avatar) et la liste de tes serveurs.
Ce qu'elle ne donne PAS : lire/envoyer tes messages en ton nom — Discord réserve ça aux bots
(automatiser un compte perso est interdit et fait bannir). Pour lire/écrire dans les serveurs,
on garde donc un bot, dont l'invitation est générée en un clic après la connexion.

Jetons stockés localement dans %APPDATA%\\Cronux\\discord_oauth.json."""
import http.server
import json
import os
import socket
import threading
import time
import urllib.parse
import webbrowser

import requests

from config import APP_DIR

API = "https://discord.com/api/v10"
TOKEN_PATH = os.path.join(APP_DIR, "discord_oauth.json")
SCOPES = "identify guilds"
UA = {"User-Agent": "Cronux (local, OAuth)"}


def _save_token(data):
    os.makedirs(APP_DIR, exist_ok=True)
    data = dict(data)
    if "expires_in" in data:
        data["expires_at"] = time.time() + int(data["expires_in"]) - 60
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _load_token():
    try:
        with open(TOKEN_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_connected():
    return _load_token() is not None


def disconnect():
    try:
        os.remove(TOKEN_PATH)
    except OSError:
        pass


# Port FIXE : il doit correspondre exactement au Redirect enregistré dans l'app Discord.
REDIRECT_PORT = 53110
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"


def _port_free():
    try:
        s = socket.socket()
        s.bind(("127.0.0.1", REDIRECT_PORT))
        s.close()
        return True
    except OSError:
        return False


def authorize_url(client_id, redirect_uri, state):
    return "https://discord.com/oauth2/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPES, "state": state, "prompt": "consent",
    })


def bot_invite_url(client_id):
    """Lien d'invitation du bot avec les permissions minimales (lire/écrire/historique)."""
    perms = 0x400 | 0x800 | 0x10000  # View Channels + Send Messages + Read Message History
    return "https://discord.com/oauth2/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "scope": "bot", "permissions": perms,
    })


class _Catcher(http.server.BaseHTTPRequestHandler):
    code = None
    state = None
    want_state = None

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Catcher.code = q.get("code", [None])[0]
        _Catcher.state = q.get("state", [None])[0]
        ok = _Catcher.code and _Catcher.state == _Catcher.want_state
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = ("Connexion réussie ! Tu peux revenir à Cronux et fermer cet onglet."
               if ok else "Échec de la connexion. Reviens à Cronux et réessaie.")
        self.wfile.write(f"<html><body style='font-family:sans-serif;text-align:center;margin-top:80px'>"
                         f"<h2>{msg}</h2></body></html>".encode("utf-8"))

    def log_message(self, *a):
        pass


def connect(client_id, client_secret, on_status=lambda s: None, timeout=180):
    """Lance la vraie connexion Discord dans le navigateur. Renvoie (ok, message)."""
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    if not client_id or not client_secret:
        return False, "Il manque le Client ID ou le Client Secret (voir « Comment l'obtenir »)."
    redirect_uri = REDIRECT_URI
    state = os.urandom(8).hex()
    _Catcher.code = _Catcher.state = None
    _Catcher.want_state = state

    try:
        server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), _Catcher)
    except OSError:
        return False, (f"Le port {REDIRECT_PORT} est déjà utilisé par un autre programme. "
                       "Ferme-le et réessaie (ce port doit rester libre pour la connexion Discord).")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    on_status("Ouverture du navigateur pour te connecter à Discord…")
    webbrowser.open(authorize_url(client_id, redirect_uri, state))

    deadline = time.time() + timeout
    while _Catcher.code is None and time.time() < deadline:
        time.sleep(0.4)
    server.shutdown()

    if _Catcher.code is None:
        return False, "Connexion annulée ou expirée."
    if _Catcher.state != state:
        return False, "Réponse de sécurité invalide, réessaie."

    on_status("Finalisation de la connexion…")
    try:
        r = requests.post(f"{API}/oauth2/token", data={
            "client_id": client_id, "client_secret": client_secret,
            "grant_type": "authorization_code", "code": _Catcher.code, "redirect_uri": redirect_uri,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
        if r.status_code != 200:
            return False, (f"Discord a refusé la connexion ({r.status_code}). Vérifie le Client Secret "
                           f"et que {redirect_uri} est bien dans les Redirects de ton app Discord.")
        tok = r.json()
        _save_token(tok)
    except Exception as e:
        return False, f"Erreur réseau : {e}"
    who = account(force=True)
    name = who.get("username", "ton compte") if who else "ton compte"
    return True, f"Connecté en tant que {name}."


def _headers():
    tok = _load_token()
    if not tok:
        return None
    return {"Authorization": f"{tok.get('token_type', 'Bearer')} {tok['access_token']}", **UA}


_CACHE = {}


def account(force=False):
    if not force and "me" in _CACHE:
        return _CACHE["me"]
    h = _headers()
    if not h:
        return None
    try:
        r = requests.get(f"{API}/users/@me", headers=h, timeout=10)
        r.raise_for_status()
        _CACHE["me"] = r.json()
        return _CACHE["me"]
    except Exception:
        return None


def my_guilds():
    h = _headers()
    if not h:
        return []
    try:
        r = requests.get(f"{API}/users/@me/guilds", headers=h, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []
