"""Outils que l'IA peut utiliser : fichiers, applications, web, Outlook, Spotify."""
import datetime
import html
import json
import locale
import os
import re
import subprocess
import sys
import time
import urllib.parse
import webbrowser

from config import APP_DIR

IS_WIN = sys.platform == "win32"
if IS_WIN:
    try:
        locale.setlocale(locale.LC_TIME, "")  # format de date de Windows (utile pour Outlook)
    except Exception:
        pass

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


class ToolError(Exception):
    pass


class Context:
    """Ce que les outils reçoivent : la config et une fonction de confirmation (fenêtre Oui/Non)."""

    def __init__(self, config, confirm):
        self.config = config
        self.confirm = confirm

    def ask(self, title, message):
        if not self.config.get("confirm_actions", True):
            return True
        return self.confirm(title, message)


REGISTRY = {}


def tool(name, description, params=None, required=(), label=None):
    def deco(fn):
        REGISTRY[name] = {
            "fn": fn,
            "label": label or name,
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {"type": "object", "properties": params or {},
                                   "required": list(required)},
                },
            },
        }
        return fn
    return deco


def schemas():
    return [t["schema"] for t in REGISTRY.values()]


def run(name, args, ctx):
    if name not in REGISTRY:
        return f"Erreur : outil inconnu '{name}'."
    try:
        result = REGISTRY[name]["fn"](ctx, **(args or {}))
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    except ToolError as e:
        return f"Erreur : {e}"
    except TypeError as e:
        return f"Erreur d'arguments pour {name} : {e}"
    except Exception as e:
        return f"Erreur pendant {name} : {type(e).__name__}: {e}"


def _open(target):
    if IS_WIN:
        os.startfile(target)
    else:
        subprocess.Popen(["xdg-open", target])


def _date_fr(dt):
    return f"{JOURS[dt.weekday()]} {dt.day} {MOIS[dt.month - 1]} {dt.year} {dt:%H:%M}"


def _parse_dt(text):
    text = (text or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ToolError(f"Date illisible '{text}'. Format attendu : AAAA-MM-JJ HH:MM.")


# ───────────────────────── Général ─────────────────────────

@tool("get_datetime", "Donne la date et l'heure actuelles.", label="Je regarde l'heure")
def get_datetime(ctx):
    return "Nous sommes le " + _date_fr(datetime.datetime.now())


# Processus système à ne pas montrer comme « applications ouvertes »
_SYS_PROC = {
    "svchost.exe", "dwm.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "smss.exe",
    "winlogon.exe", "fontdrvhost.exe", "sihost.exe", "taskhostw.exe", "ctfmon.exe", "conhost.exe",
    "runtimebroker.exe", "searchhost.exe", "searchindexer.exe", "shellexperiencehost.exe", "dllhost.exe",
    "registry", "memory compression", "system", "system idle process", "spoolsv.exe", "audiodg.exe",
    "wmiprvse.exe", "startmenuexperiencehost.exe", "textinputhost.exe", "applicationframehost.exe",
    "backgroundtaskhost.exe", "securityhealthservice.exe", "securityhealthsystray.exe", "nvcontainer.exe",
    "msmpeng.exe", "wudfhost.exe", "rundll32.exe", "explorer.exe", "widgets.exe", "lockapp.exe",
    "cronux.exe", "cronux-update.exe", "pythonw.exe",
}


def list_processes(top=15):
    """Applications visibles actuellement ouvertes, triées par mémoire utilisée. Renvoie une liste de dicts."""
    try:
        import psutil
    except ImportError:
        return None
    apps = {}
    for p in psutil.process_iter(["name", "exe", "memory_info"]):
        try:
            name = (p.info.get("name") or "").strip()
            low = name.lower()
            if not name or low in _SYS_PROC or not p.info.get("exe"):
                continue
            ex = p.info["exe"].lower()
            if "\\windows\\" in ex and "\\system32\\" in ex:
                continue
            mem = p.info["memory_info"].rss if p.info.get("memory_info") else 0
            pretty = name[:-4] if low.endswith(".exe") else name
            cur = apps.setdefault(pretty, {"name": pretty, "mem": 0, "count": 0})
            cur["mem"] += mem
            cur["count"] += 1
        except Exception:
            continue
    return sorted(apps.values(), key=lambda a: -a["mem"])[:top]


@tool("list_running_apps", "Montre les applications et jeux actuellement ouverts sur le PC (triés par mémoire utilisée).",
      {"count": {"type": "integer", "description": "Nombre, défaut 12"}},
      label="Je regarde ce qui est ouvert")
def list_running_apps(ctx, count=12):
    if not IS_WIN:
        return "Lisible uniquement sous Windows."
    apps = list_processes(min(int(count or 12), 30))
    if apps is None:
        return "Le module psutil manque."
    if not apps:
        return "Aucune application visible détectée."
    return "Applications ouvertes :\n" + "\n".join(
        f"- {a['name']} ({a['mem'] / 1024 ** 2:.0f} Mo)" for a in apps)


@tool("open_url", "Ouvre une adresse web, ou lance une recherche Google si ce n'est pas une adresse.",
      {"url_or_query": {"type": "string", "description": "URL ou texte à rechercher"}},
      required=["url_or_query"], label="J'ouvre le navigateur")
def open_url(ctx, url_or_query):
    s = url_or_query.strip()
    if not s.startswith(("http://", "https://")):
        if "." in s and " " not in s:
            s = "https://" + s
        else:
            s = "https://www.google.com/search?q=" + urllib.parse.quote(s)
    webbrowser.open(s)
    return f"Ouvert : {s}"


UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"}


def _strip_tags(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


@tool("web_search", "Cherche sur Internet et renvoie les meilleurs résultats (titre, lien, extrait). "
                    "Utile pour les guides et wikis de jeux, l'actu, la météo, une info précise.",
      {"query": {"type": "string"}}, required=["query"], label="Je cherche sur Internet")
def web_search(ctx, query):
    import requests
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "fr-fr"},
                      headers=UA, timeout=15)
    r.raise_for_status()
    blocks = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
                        r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.S)
    out = []
    for href, title, snippet in blocks[:6]:
        if "uddg=" in href:
            href = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                                        .get("uddg", [href])[0])
        out.append(f"- {_strip_tags(title)}\n  {href}\n  {_strip_tags(snippet)}")
    return "\n".join(out) if out else "Aucun résultat (le moteur a peut-être bloqué la requête)."


@tool("web_read", "Lit le texte d'une page web (ex. un guide trouvé avec web_search).",
      {"url": {"type": "string"}, "focus": {"type": "string", "description": "Optionnel : mot à chercher dans la page"}},
      required=["url"], label="Je lis la page")
def web_read(ctx, url, focus=None):
    import requests
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    page = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer)[^>]*>.*?</\1>", " ", r.text)
    text = _strip_tags(page)
    if focus:
        hits = [m.start() for m in re.finditer(re.escape(focus), text, re.I)][:5]
        if hits:
            return "\n…\n".join(text[max(0, h - 600):h + 900] for h in hits)[:6000]
    return text[:6000]


# ───────────────────────── Fichiers ─────────────────────────

SKIP_DIRS = {"node_modules", ".git", "appdata", "$recycle.bin", "__pycache__", "venv", ".venv"}


def _search_roots(ctx):
    custom = [p for p in ctx.config.get("search_folders", []) if os.path.isdir(p)]
    if custom:
        return custom
    home = os.path.expanduser("~")
    names = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos",
             "OneDrive", "Bureau", "Images", "Musique", "Vidéos", "Téléchargements"]
    roots, seen = [], set()
    for n in names:
        p = os.path.join(home, n)
        rp = os.path.realpath(p).lower()
        if os.path.isdir(p) and rp not in seen:
            seen.add(rp)
            roots.append(p)
    return roots or [home]


@tool("search_files",
      "Cherche des fichiers ou dossiers sur l'ordinateur par mots du nom (Bureau, Documents, "
      "Téléchargements, Images, Musique, Vidéos, OneDrive). Renvoie les chemins complets.",
      {"query": {"type": "string", "description": "Mots du nom de fichier, ex. 'facture edf'"},
       "extension": {"type": "string", "description": "Optionnel, ex. 'pdf', 'docx', 'jpg'"}},
      required=["query"], label="Je cherche les fichiers")
def search_files(ctx, query, extension=None):
    words = [w for w in query.lower().split() if w]
    ext = ("." + extension.lower().lstrip(".")) if extension else None
    if not words and not ext:
        raise ToolError("Donne au moins un mot à chercher.")
    results, deadline = [], time.time() + 15
    for root in _search_roots(ctx):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d.lower() not in SKIP_DIRS]
            for name, is_dir in [(d, True) for d in dirnames] + [(f, False) for f in filenames]:
                low = name.lower()
                if ext and (is_dir or not low.endswith(ext)):
                    continue
                if all(w in low for w in words):
                    full = os.path.join(dirpath, name)
                    try:
                        mtime = os.path.getmtime(full)
                    except OSError:
                        mtime = 0
                    results.append((mtime, full, is_dir))
            if time.time() > deadline or len(results) > 300:
                break
    if not results:
        return f"Aucun fichier trouvé pour « {query} »."
    results.sort(reverse=True)
    lines = [f"{'[dossier] ' if d else ''}{p}  (modifié le {datetime.datetime.fromtimestamp(m):%d/%m/%Y})"
             for m, p, d in results[:15]]
    return f"{len(results)} résultat(s), les plus récents :\n" + "\n".join(lines)


@tool("open_path", "Ouvre un fichier ou un dossier avec son application par défaut, "
                   "ou le montre dans l'Explorateur.",
      {"path": {"type": "string", "description": "Chemin complet"},
       "show_in_explorer": {"type": "boolean", "description": "true pour juste le sélectionner dans l'Explorateur"}},
      required=["path"], label="J'ouvre le fichier")
def open_path(ctx, path, show_in_explorer=False):
    if not os.path.exists(path):
        raise ToolError(f"Le chemin n'existe pas : {path}")
    if show_in_explorer and IS_WIN:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        _open(path)
    return f"Ouvert : {path}"


# ───────────────────────── Applications ─────────────────────────

APP_ALIASES = {
    "calculatrice": "calc", "calculette": "calc", "bloc-notes": "notepad", "bloc notes": "notepad",
    "explorateur": "explorer", "explorateur de fichiers": "explorer",
    "paramètres": "ms-settings:", "parametres": "ms-settings:", "réglages": "ms-settings:",
    "spotify": "spotify:", "gestionnaire des tâches": "taskmgr", "paint": "mspaint",
    "invite de commandes": "cmd", "terminal": "wt",
}


def _start_menu_shortcuts():
    dirs = [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                         r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.path.expanduser("~"), "Desktop")]
    for d in dirs:
        if os.path.isdir(d):
            for dirpath, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".lnk", ".url")):
                        yield os.path.splitext(f)[0], os.path.join(dirpath, f)


@tool("launch_app", "Lance une application installée (ex. Spotify, Outlook, Word, Chrome, Discord, calculatrice).",
      {"name": {"type": "string", "description": "Nom de l'application"}},
      required=["name"], label="Je lance l'application")
def launch_app(ctx, name):
    key = name.strip().lower()
    if key in APP_ALIASES:
        target = APP_ALIASES[key]
        if target.endswith(":"):
            _open(target)
        else:
            subprocess.Popen(target, shell=True)
        return f"{name} lancé."
    matches = [(n, p) for n, p in _start_menu_shortcuts() if key in n.lower()]
    if matches:
        matches.sort(key=lambda m: (m[0].lower() != key, "désinstall" in m[0].lower()
                                    or "uninstall" in m[0].lower(), len(m[0])))
        _open(matches[0][1])
        return f"{matches[0][0]} lancé."
    try:
        _open(key)
        return f"{name} lancé."
    except Exception:
        raise ToolError(f"Je ne trouve pas d'application nommée « {name} ».")


# ───────────────────────── Outlook (mail + agenda) ─────────────────────────

_MAIL_CACHE = {}


def _outlook():
    if not IS_WIN:
        raise ToolError("Outlook n'est disponible que sous Windows.")
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        raise ToolError("Le module pywin32 manque.")
    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch("Outlook.Application")
        return app, app.GetNamespace("MAPI")
    except Exception:
        raise ToolError("Impossible de joindre Outlook. Il faut l'Outlook « classique » installé "
                        "(le « nouvel Outlook » ne permet pas l'automatisation).")


def _od(dt):
    """Date au format attendu par Outlook (format régional de Windows)."""
    return dt.strftime("%x %H:%M")


def _cd(com_dt):
    try:
        return _date_fr(datetime.datetime(com_dt.year, com_dt.month, com_dt.day,
                                          com_dt.hour, com_dt.minute))
    except Exception:
        return str(com_dt)


@tool("list_events", "Liste les rendez-vous de l'agenda Outlook sur une période.",
      {"start_date": {"type": "string", "description": "AAAA-MM-JJ, par défaut aujourd'hui"},
       "days": {"type": "integer", "description": "Nombre de jours à couvrir (défaut 7)"}},
      label="Je consulte l'agenda")
def list_events(ctx, start_date=None, days=7):
    _, ns = _outlook()
    start = _parse_dt(start_date) if start_date else datetime.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=int(days or 7))
    items = ns.GetDefaultFolder(9).Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")
    found = items.Restrict(f"[Start] < '{_od(end)}' AND [End] > '{_od(start)}'")
    out, it = [], found.GetFirst()
    while it is not None and len(out) < 60:
        line = f"- {_cd(it.Start)} → {it.End.hour:02d}:{it.End.minute:02d} : {it.Subject}"
        if it.Location:
            line += f" ({it.Location})"
        out.append(line)
        it = found.GetNext()
    if not out:
        return f"Aucun rendez-vous du {start:%d/%m} au {end:%d/%m}."
    return "\n".join(out)


@tool("create_event", "Crée un rendez-vous dans l'agenda Outlook.",
      {"title": {"type": "string"},
       "start": {"type": "string", "description": "AAAA-MM-JJ HH:MM"},
       "duration_minutes": {"type": "integer", "description": "Durée, défaut 60"},
       "location": {"type": "string"},
       "reminder_minutes": {"type": "integer", "description": "Rappel avant, défaut 15"}},
      required=["title", "start"], label="J'ajoute le rendez-vous")
def create_event(ctx, title, start, duration_minutes=60, location="", reminder_minutes=15):
    dt = _parse_dt(start)
    msg = f"{title}\n{_date_fr(dt)} ({duration_minutes} min)" + (f"\nLieu : {location}" if location else "")
    if not ctx.ask("Ajouter ce rendez-vous ?", msg):
        return "L'utilisateur a annulé la création du rendez-vous."
    app, _ = _outlook()
    appt = app.CreateItem(1)
    appt.Subject = title
    appt.Start = _od(dt)
    appt.Duration = int(duration_minutes or 60)
    appt.Location = location or ""
    appt.ReminderSet = True
    appt.ReminderMinutesBeforeStart = int(reminder_minutes or 15)
    appt.Save()
    return f"Rendez-vous créé : {msg}"


def _mail_lines(collection, count):
    out, it = [], collection.GetFirst()
    while it is not None and len(out) < count:
        if getattr(it, "Class", None) == 43:  # MailItem
            idx = len(_MAIL_CACHE) + 1
            _MAIL_CACHE[idx] = it.EntryID
            preview = " ".join((it.Body or "").split())[:140]
            out.append(f"[id {idx}] {'(non lu) ' if it.UnRead else ''}{_cd(it.ReceivedTime)} — "
                       f"de {it.SenderName} — « {it.Subject} » — {preview}")
        it = collection.GetNext()
    return out


@tool("list_emails", "Liste les derniers e-mails de la boîte de réception Outlook (ou des envoyés).",
      {"count": {"type": "integer", "description": "Nombre, défaut 10"},
       "unread_only": {"type": "boolean"},
       "folder": {"type": "string", "enum": ["inbox", "sent"]}},
      label="Je regarde les mails")
def list_emails(ctx, count=10, unread_only=False, folder="inbox"):
    _, ns = _outlook()
    items = ns.GetDefaultFolder(5 if folder == "sent" else 6).Items
    items.Sort("[ReceivedTime]", True)
    if unread_only:
        items = items.Restrict("[UnRead] = True")
    out = _mail_lines(items, min(int(count or 10), 30))
    return "\n".join(out) if out else "Aucun e-mail."


@tool("search_emails", "Cherche des e-mails Outlook par mot dans l'objet, le texte ou l'expéditeur.",
      {"query": {"type": "string"}, "count": {"type": "integer"}},
      required=["query"], label="Je cherche dans les mails")
def search_emails(ctx, query, count=10):
    _, ns = _outlook()
    q = query.replace("'", "''")
    f = (f"@SQL=\"urn:schemas:httpmail:subject\" LIKE '%{q}%' OR "
         f"\"urn:schemas:httpmail:fromname\" LIKE '%{q}%' OR "
         f"\"urn:schemas:httpmail:textdescription\" LIKE '%{q}%'")
    items = ns.GetDefaultFolder(6).Items
    items.Sort("[ReceivedTime]", True)
    out = _mail_lines(items.Restrict(f), min(int(count or 10), 30))
    return "\n".join(out) if out else f"Aucun e-mail trouvé pour « {query} »."


def _mail_by_id(ns, id):
    entry = _MAIL_CACHE.get(int(id))
    if not entry:
        raise ToolError("id d'e-mail inconnu : liste ou cherche d'abord les e-mails.")
    return ns.GetItemFromID(entry)


@tool("read_email", "Lit le contenu complet d'un e-mail (id obtenu via list_emails ou search_emails).",
      {"id": {"type": "integer"}}, required=["id"], label="Je lis le mail")
def read_email(ctx, id):
    _, ns = _outlook()
    m = _mail_by_id(ns, id)
    return (f"De : {m.SenderName} <{m.SenderEmailAddress}>\nÀ : {m.To}\nDate : {_cd(m.ReceivedTime)}\n"
            f"Objet : {m.Subject}\n\n{(m.Body or '')[:4000]}")


@tool("send_email", "Envoie un nouvel e-mail avec Outlook (l'utilisateur confirme avant l'envoi).",
      {"to": {"type": "string", "description": "Adresse(s), séparées par ;"},
       "subject": {"type": "string"}, "body": {"type": "string"},
       "cc": {"type": "string"}},
      required=["to", "subject", "body"], label="Je prépare le mail")
def send_email(ctx, to, subject, body, cc=""):
    if not ctx.ask("Envoyer ce mail ?", f"À : {to}\nObjet : {subject}\n\n{body}"):
        return "L'utilisateur a annulé l'envoi."
    app, _ = _outlook()
    m = app.CreateItem(0)
    m.To, m.Subject, m.Body = to, subject, body
    if cc:
        m.CC = cc
    m.Send()
    return f"E-mail envoyé à {to}."


@tool("reply_email", "Répond à un e-mail (id obtenu via list_emails ou search_emails).",
      {"id": {"type": "integer"}, "body": {"type": "string"}},
      required=["id", "body"], label="Je prépare la réponse")
def reply_email(ctx, id, body):
    _, ns = _outlook()
    m = _mail_by_id(ns, id)
    if not ctx.ask("Envoyer cette réponse ?", f"À : {m.SenderName}\nObjet : RE: {m.Subject}\n\n{body}"):
        return "L'utilisateur a annulé la réponse."
    r = m.Reply()
    r.Body = body + "\n\n" + (r.Body or "")
    r.Send()
    return f"Réponse envoyée à {m.SenderName}."


# ───────────────────────── Spotify ─────────────────────────

_SP = None
SP_SCOPE = "user-modify-playback-state user-read-playback-state user-read-currently-playing"


def _spotify(ctx):
    global _SP
    if _SP:
        return _SP
    cid = ctx.config.get("spotify_client_id", "").strip()
    if not cid:
        raise ToolError("Spotify n'est pas configuré : ajoute ton spotify_client_id dans les "
                        "réglages (bouton ⚙). Voir le LISEZMOI.")
    import spotipy
    from spotipy.cache_handler import CacheFileHandler
    from spotipy.oauth2 import SpotifyPKCE
    auth = SpotifyPKCE(client_id=cid, redirect_uri=ctx.config["spotify_redirect_uri"],
                       scope=SP_SCOPE, open_browser=True,
                       cache_handler=CacheFileHandler(cache_path=os.path.join(APP_DIR, ".spotify_cache")))
    _SP = spotipy.Spotify(auth_manager=auth)
    return _SP


def _device(sp):
    devices = sp.devices().get("devices", [])
    for d in devices:
        if d.get("is_active"):
            return d["id"]
    if not devices:
        _open("spotify:")
        for _ in range(12):
            time.sleep(1)
            devices = sp.devices().get("devices", [])
            if devices:
                break
    if not devices:
        raise ToolError("Aucun appareil Spotify trouvé. Ouvre Spotify puis réessaie.")
    devices.sort(key=lambda d: d.get("type") != "Computer")
    return devices[0]["id"]


@tool("spotify_play", "Joue de la musique sur Spotify : un titre, un artiste, un album ou une playlist. "
                      "Sans query, reprend la lecture.",
      {"query": {"type": "string", "description": "Ce qu'il faut chercher, ex. 'Bohemian Rhapsody Queen'"},
       "kind": {"type": "string", "enum": ["track", "artist", "album", "playlist"],
                "description": "Type de recherche, défaut track"}},
      label="Je lance la musique")
def spotify_play(ctx, query="", kind="track"):
    sp = _spotify(ctx)
    dev = _device(sp)
    if not query:
        sp.start_playback(device_id=dev)
        return "Lecture reprise."
    kind = kind if kind in ("track", "artist", "album", "playlist") else "track"
    items = [i for i in sp.search(q=query, type=kind, limit=3)[kind + "s"]["items"] if i]
    if not items:
        return f"Rien trouvé sur Spotify pour « {query} »."
    it = items[0]
    if kind == "track":
        sp.start_playback(device_id=dev, uris=[it["uri"]])
        return f"Lecture : {it['name']} — {', '.join(a['name'] for a in it['artists'])}"
    sp.start_playback(device_id=dev, context_uri=it["uri"])
    return f"Lecture ({kind}) : {it['name']}"


@tool("spotify_control", "Contrôle Spotify : pause, reprise, suivant, précédent, volume, aléatoire.",
      {"action": {"type": "string", "enum": ["pause", "resume", "next", "previous",
                                              "volume", "shuffle_on", "shuffle_off"]},
       "volume_percent": {"type": "integer", "description": "0-100, pour action=volume"}},
      required=["action"], label="Je contrôle Spotify")
def spotify_control(ctx, action, volume_percent=None):
    sp = _spotify(ctx)
    dev = _device(sp)
    if action == "pause":
        sp.pause_playback(device_id=dev)
    elif action == "resume":
        sp.start_playback(device_id=dev)
    elif action == "next":
        sp.next_track(device_id=dev)
    elif action == "previous":
        sp.previous_track(device_id=dev)
    elif action == "volume":
        sp.volume(max(0, min(100, int(volume_percent if volume_percent is not None else 50))), device_id=dev)
    elif action in ("shuffle_on", "shuffle_off"):
        sp.shuffle(action == "shuffle_on", device_id=dev)
    else:
        raise ToolError(f"Action inconnue : {action}")
    return f"OK ({action})."


@tool("spotify_now_playing", "Indique le morceau en cours sur Spotify.", label="Je regarde Spotify")
def spotify_now_playing(ctx):
    cur = _spotify(ctx).current_playback()
    if not cur or not cur.get("item"):
        return "Rien en lecture."
    it = cur["item"]
    artists = ", ".join(a["name"] for a in it.get("artists", []))
    return f"{'En lecture' if cur.get('is_playing') else 'En pause'} : {it['name']} — {artists}"
