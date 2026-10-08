"""Notifications Windows (Discord, mails, apps…) : lecture, tri important / pas important.

Windows garde les notifications dans %LOCALAPPDATA%\\Microsoft\\Windows\\Notifications\\wpndatabase.db.
On en lit une copie (sans jamais modifier l'original) et on garde notre propre historique trié."""
import contextlib
import copy
import datetime
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import xml.etree.ElementTree as ET

from config import APP_DIR
from tools import IS_WIN, tool

STORE = os.path.join(APP_DIR, "notifications.json")
DB = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Windows\Notifications\wpndatabase.db")
_LOCK = threading.Lock()
MAX_ITEMS = 300
IGNORE_APPS = ("cronux", "python")

KNOWN_APPS = [("discord", "Discord"), ("outlook", "Outlook"), ("spotify", "Spotify"),
              ("whatsapp", "WhatsApp"), ("teams", "Teams"), ("chrome", "Chrome"), ("msedge", "Edge"),
              ("firefox", "Firefox"), ("steam", "Steam"), ("telegram", "Telegram"),
              ("messenger", "Messenger"), ("instagram", "Instagram"), ("signal", "Signal"),
              ("windows.defender", "Sécurité Windows"), ("securityhealth", "Sécurité Windows")]

URGENT_WORDS = ("urgent", "important", "asap", "vite", "appel manqué", "missed call", "code",
                "vérification", "verification", "paiement", "payment", "connexion", "sign-in",
                "livraison", "colis", "rendez-vous", "rappel", "@")


_CACHE = {"stamp": None, "data": None}


def _stamp():
    try:
        st = os.stat(STORE)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def _peek():
    """Historique en LECTURE SEULE, relu seulement si le fichier a changé (le badge 🔔 et le panneau
    le consultent très souvent)."""
    stamp = _stamp()
    if _CACHE["data"] is not None and stamp == _CACHE["stamp"]:
        return _CACHE["data"]
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}
    d.setdefault("last_id", 0)
    d.setdefault("items", [])
    _CACHE.update(stamp=stamp, data=d)
    return d


def _load():
    """Copie modifiable (pour les écritures, sous _LOCK)."""
    return copy.deepcopy(_peek())


def _save(d):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)
    _CACHE.update(stamp=_stamp(), data=copy.deepcopy(d))


def _app_name(primary):
    low = (primary or "").lower()
    for key, name in KNOWN_APPS:
        if key in low:
            return name
    p = (primary or "").split("!")[0].split("_")[0]
    p = p.replace("\\", "/").split("/")[-1]
    if p.lower().endswith(".exe"):
        p = p[:-4]
    return (p.split(".")[-1] or "Windows")[:40]


def _texts(payload):
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", "ignore")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return "", ""
    texts = [(t.text or "").strip() for t in root.iter("text") if (t.text or "").strip()]
    return (texts[0] if texts else ""), " — ".join(texts[1:])


def _filetime(ft):
    try:
        utc = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=int(ft) // 10)
        return utc.replace(tzinfo=datetime.timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def read_db(after_id, limit, db_path=None):
    """Renvoie (plus grand id vu, notifications) postérieures à after_id."""
    db_path = db_path or DB
    if not os.path.exists(db_path):
        return after_id, []
    tmp = tempfile.mkdtemp(prefix="cronux_")
    try:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db_path + suffix):
                shutil.copy2(db_path + suffix, os.path.join(tmp, "wpn.db" + suffix))
        with contextlib.closing(sqlite3.connect(os.path.join(tmp, "wpn.db"))) as con:
            rows = con.execute(
                "SELECT n.Id, h.PrimaryId, n.Payload, n.ArrivalTime FROM Notification n "
                "JOIN NotificationHandler h ON n.HandlerId = h.RecordId "
                "WHERE n.Type = 'toast' AND n.Id > ? ORDER BY n.Id DESC LIMIT ?", (after_id, limit)).fetchall()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    max_id, out = after_id, []
    for nid, primary, payload, arrival in reversed(rows):
        max_id = max(max_id, nid)
        app = _app_name(primary)
        if any(x in app.lower() for x in IGNORE_APPS):
            continue
        title, body = _texts(payload)
        if not title and not body:
            continue
        out.append({"id": nid, "app": app, "title": title[:200], "body": body[:600],
                    "time": _filetime(arrival), "important": False, "reason": "", "seen": False})
    return max_id, out


_MTIME = {"v": None}


def _mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:  # absent, ou supprimé entre deux vérifications
        return 0


def db_changed():
    """Vrai si Windows a écrit une nouvelle notification depuis le dernier passage (évite des copies inutiles)."""
    stamp = tuple(_mtime(DB + s) for s in ("", "-wal"))
    changed = stamp != _MTIME["v"]
    _MTIME["v"] = stamp
    return changed


def fetch_new():
    """Nouvelles notifications depuis la dernière vérification. Renvoie (liste, premier_lancement)."""
    if not IS_WIN:
        return [], False
    last = _peek()["last_id"]
    first = last == 0
    max_id, items = read_db(last, 15 if first else 100)
    if max_id != last and not items:
        with _LOCK:
            d = _load()
            d["last_id"] = max(d["last_id"], max_id)
            _save(d)
    for i in items:
        i["_max_id"] = max_id
    return items, first


RULE_RE = re.compile(r"\[notif\] Les notifications de (.+?) « (.*?) » (sont importantes|ne sont pas importantes)")


def learned_rules():
    """Règles apprises quand tu corriges le tri (bouton du panneau) : {(app, titre[:60]) : important}.
    Lues une fois par lot de notifications au lieu d'une fois par notification."""
    import memory
    rules = {}
    for f in memory._peek()["facts"]:  # dans l'ordre : la règle la plus récente l'emporte
        m = RULE_RE.search(f["text"])
        if m:
            rules[(m.group(1).lower(), m.group(2).lower())] = m.group(3) == "sont importantes"
    return rules


def learned_rule(item, rules=None):
    """Règle apprise pour cette notification : True / False, ou None s'il n'y en a pas."""
    rules = learned_rules() if rules is None else rules
    return rules.get((item["app"].lower(), item["title"][:60].lower()))


def heuristic(item):
    text = f"{item['title']} {item['body']}".lower()
    item["important"] = any(w in text for w in URGENT_WORDS)
    item["reason"] = "mot-clé" if item["important"] else "pas de signe d'urgence"
    return item


def add(items, seen=False):
    with _LOCK:
        d = _load()
        known = {i["id"] for i in d["items"]}
        for i in items:
            d["last_id"] = max(d["last_id"], i.pop("_max_id", i["id"]), i["id"])
            if i["id"] not in known:
                i["seen"] = seen or not i.get("important")
                d["items"].append(i)
        d["items"] = d["items"][-MAX_ITEMS:]
        _save(d)


def recent(only_important=None, app=None, count=20):
    items = _peek()["items"]
    if only_important is not None:
        items = [i for i in items if bool(i.get("important")) == bool(only_important)]
    if app:
        items = [i for i in items if app.lower() in i["app"].lower()]
    return copy.deepcopy(items[::-1][:count])


def set_importance(nid, important):
    with _LOCK:
        d = _load()
        for i in d["items"]:
            if i["id"] == nid:
                i["important"] = bool(important)
                i["reason"] = "choisi par toi"
                i["seen"] = True
        _save(d)


def unseen_important():
    return sum(1 for i in _peek()["items"] if i.get("important") and not i.get("seen"))


def mark_all_seen():
    with _LOCK:
        if all(i.get("seen") for i in _peek()["items"]):
            return  # rien à écrire
        d = _load()
        for i in d["items"]:
            i["seen"] = True
        _save(d)


@tool("list_notifications",
      "Montre les notifications Windows récentes (messages Discord, mails, apps…), déjà triées en "
      "importantes ou non. Utilise app='Discord' pour les messages Discord reçus.",
      {"only_important": {"type": "boolean", "description": "true = seulement les importantes"},
       "app": {"type": "string", "description": "Filtrer par application, ex. Discord"},
       "count": {"type": "integer", "description": "Nombre, défaut 15"}},
      label="Je regarde les notifications")
def list_notifications(ctx, only_important=None, app=None, count=15):
    if not IS_WIN:
        return "Les notifications ne sont lisibles que sous Windows."
    items = recent(only_important, app, min(int(count or 15), 50))
    if not items:
        return "Aucune notification correspondante."
    return "\n".join(f"[{'IMPORTANT' if i['important'] else 'normal'}] {i['time']} — {i['app']} — "
                     f"{i['title']} : {i['body']}" for i in items)
