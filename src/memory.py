"""Mémoire à long terme : faits retenus, habitudes d'utilisation et conversation précédente.
Tout est stocké localement dans %APPDATA%\\Cronux\\memoire.json."""
import copy
import datetime
import json
import os
import threading

from config import APP_DIR
from tools import ToolError, tool

PATH = os.path.join(APP_DIR, "memoire.json")
_LOCK = threading.Lock()
MAX_FACTS = 200


_CACHE = {"stamp": None, "data": None}


def _stamp():
    try:
        st = os.stat(PATH)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def _normalize(data):
    if not isinstance(data, dict):
        data = {}
    data.setdefault("facts", [])
    data.setdefault("habits", {})
    data.setdefault("last_conversation", [])
    return data


def _peek():
    """Données en LECTURE SEULE (ne pas modifier) : relit le fichier seulement s'il a changé.
    La mémoire est lue à chaque étape de réflexion et pour chaque notification : sans ce cache,
    le JSON était relu et re-parsé des dizaines de fois par minute."""
    stamp = _stamp()
    if _CACHE["data"] is not None and stamp == _CACHE["stamp"]:
        return _CACHE["data"]
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data = _normalize(data)
    _CACHE.update(stamp=stamp, data=data)
    return data


def _load():
    """Copie modifiable des données (pour les écritures, sous _LOCK)."""
    return copy.deepcopy(_peek())


def _save(data):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, PATH)
    _CACHE.update(stamp=_stamp(), data=_normalize(copy.deepcopy(data)))


# ───────── Faits retenus (l'IA les gère elle-même via des outils) ─────────

@tool("remember", "Mémorise durablement une information utile sur l'utilisateur : préférences, "
                  "proches, contacts mail, habitudes, projets, façon de parler. À utiliser de ta propre "
                  "initiative dès que l'utilisateur révèle quelque chose qui servira plus tard.",
      {"fact": {"type": "string", "description": "Phrase courte, ex. 'Sa sœur s'appelle Léa (lea@mail.com)'"}},
      required=["fact"], label="Je retiens ça")
def remember(ctx, fact):
    fact = fact.strip()
    if not fact:
        raise ToolError("Rien à retenir.")
    with _LOCK:
        data = _load()
        if any(f["text"].lower() == fact.lower() for f in data["facts"]):
            return "Déjà en mémoire."
        data["facts"].append({"id": max([f["id"] for f in data["facts"]] or [0]) + 1,
                              "text": fact, "date": f"{datetime.date.today():%Y-%m-%d}"})
        data["facts"] = data["facts"][-MAX_FACTS:]
        _save(data)
    return f"Retenu : {fact}"


@tool("forget", "Oublie une information mémorisée (quand elle est fausse, périmée, ou si l'utilisateur le demande).",
      {"id": {"type": "integer", "description": "id du souvenir (voir la liste dans tes instructions)"}},
      required=["id"], label="J'oublie ça")
def forget(ctx, id):
    with _LOCK:
        data = _load()
        before = len(data["facts"])
        data["facts"] = [f for f in data["facts"] if f["id"] != int(id)]
        if len(data["facts"]) == before:
            raise ToolError(f"Aucun souvenir avec l'id {id}.")
        _save(data)
    return "Oublié."


# ───────── Habitudes (enregistrées automatiquement) ─────────

def _habit_key(name, args):
    if name == "launch_app":
        return "app", args.get("name", "").strip().lower()
    if name == "open_path":
        return "fichier", args.get("path", "")
    if name == "spotify_play" and args.get("query"):
        return "musique", f"{args.get('query')} ({args.get('kind', 'track')})"
    if name == "open_url":
        return "web", args.get("url_or_query", "")
    if name in ("send_email", "reply_email") and args.get("to"):
        return "contact", args.get("to")
    return None, None


def record_usage(name, args, result):
    if result.startswith("Erreur") or "annulé" in result:
        return
    cat, key = _habit_key(name, args or {})
    if name == "detect_game" and result.startswith("Jeu en cours"):
        cat, key = "jeu", result.split("\n")[0].split(":", 1)[1].strip()
    if not key:
        return
    hour = datetime.datetime.now().hour
    moment = "matin" if hour < 12 else "après-midi" if hour < 18 else "soir"
    with _LOCK:
        data = _load()
        h = data["habits"].setdefault(cat, {}).setdefault(key, {"count": 0, "moments": {}})
        h["count"] += 1
        h["moments"][moment] = h["moments"].get(moment, 0) + 1
        h["last"] = f"{datetime.date.today():%Y-%m-%d}"
        _save(data)


# ───────── Conversation précédente (pour reprendre là où on s'est arrêté) ─────────

def save_conversation(history):
    msgs = [m for m in history if m.get("role") in ("user", "assistant") and m.get("content")]
    with _LOCK:
        data = _load()
        data["last_conversation"] = [{"role": m["role"], "content": m["content"][:600]} for m in msgs[-12:]]
        _save(data)


def last_conversation():
    return copy.deepcopy(_peek()["last_conversation"])


def clear_all():
    with _LOCK:
        _save({"facts": [], "habits": {}, "last_conversation": []})


def all_facts():
    return copy.deepcopy(_peek()["facts"])


def delete_fact(fact_id):
    forget(None, fact_id)


def add_fact(text):
    return remember(None, text)


def habits_summary():
    out = []
    for cat, entries in _peek()["habits"].items():
        for key, h in sorted(entries.items(), key=lambda kv: -kv[1]["count"]):
            if h["count"] >= 2:
                moment = max(h["moments"], key=h["moments"].get)
                out.append(f"{cat} · {key} — {h['count']}×, surtout le {moment}")
    return out


# ───────── Résumé injecté dans les instructions de l'IA ─────────

def prompt_block():
    data = _peek()
    parts = []
    if data["facts"]:
        parts.append("CE QUE TU SAIS SUR L'UTILISATEUR (id: souvenir) :\n" +
                     "\n".join(f"{f['id']}: {f['text']}" for f in data["facts"]))
    habit_lines = []
    for cat, entries in data["habits"].items():
        top = sorted(entries.items(), key=lambda kv: -kv[1]["count"])[:6]
        for key, h in top:
            if h["count"] >= 2:
                moment = max(h["moments"], key=h["moments"].get)
                habit_lines.append(f"- {cat} : {key} — {h['count']} fois, surtout le {moment}")
    if habit_lines:
        parts.append("SES HABITUDES (observées automatiquement) :\n" + "\n".join(habit_lines))
    return "\n\n".join(parts)
