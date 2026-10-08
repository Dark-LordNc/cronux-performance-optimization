"""Jeux : détection du jeu lancé et recherche dans ses fichiers (données + sauvegardes).

Lecture des fichiers sur disque uniquement : Cronux ne lit jamais la mémoire d'un jeu et ne modifie rien."""
import json
import os
import re
import time
import urllib.parse

from tools import UA, ToolError, tool, web_search

_LAST = {"name": None, "root": None}

LIBRARY_HINTS = [r"\steamapps\common", r"\epic games", r"\riot games", r"\gog galaxy\games",
                 r"\gog games", r"\ubisoft game launcher\games", r"\ea games", r"\xboxgames",
                 r"\program files\electronic arts", r"\games"]

IGNORE_EXE = {
    "steam.exe", "steamwebhelper.exe", "steamservice.exe", "epicgameslauncher.exe", "epicwebhelper.exe",
    "riotclientservices.exe", "riotclientux.exe", "riotclientuxrender.exe", "riotclientcrashhandler.exe",
    "vgc.exe", "vgtray.exe", "unitycrashhandler64.exe", "unitycrashhandler32.exe", "crashreportclient.exe",
    "easyanticheat.exe", "easyanticheat_eos.exe", "beservice.exe", "beservice_x64.exe", "eadesktop.exe",
    "eabackgroundservice.exe", "upc.exe", "ubisoftconnect.exe", "uplaywebcore.exe", "galaxyclient.exe",
    "battle.net.exe", "agent.exe", "redprelauncher.exe", "redlauncher.exe", "overwolf.exe", "gamebarpresencewriter.exe", "crashpad_handler.exe",
}
NOT_GAMES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe", "discord.exe", "spotify.exe",
    "explorer.exe", "code.exe", "devenv.exe", "ollama.exe", "ollama_llama_server.exe", "llama-server.exe",
    "cronux.exe", "python.exe", "pythonw.exe", "msmpeng.exe", "searchhost.exe", "dwm.exe", "teams.exe",
    "ms-teams.exe", "outlook.exe", "winword.exe", "excel.exe", "obs64.exe", "memory compression",
    "system", "svchost.exe", "nvcontainer.exe", "photoshop.exe", "blender.exe", "msedgewebview2.exe",
}
TEXT_EXT = {".json", ".xml", ".ini", ".cfg", ".txt", ".lua", ".csv", ".tsv", ".yaml", ".yml", ".toml",
            ".ltx", ".properties", ".js", ".md", ".html", ".htm", ".conf", ".vdf", ".acf", ".log"}
SKIP_EXT = {".dll", ".exe", ".png", ".jpg", ".jpeg", ".dds", ".tga", ".bmp", ".wav", ".ogg", ".mp3",
            ".mp4", ".webm", ".bik", ".bk2", ".usm", ".wem", ".bnk", ".ttf", ".otf", ".fnt", ".pdb",
            ".so", ".mov", ".avi", ".ktx", ".ico", ".cur", ".pyc", ".zip", ".7z", ".rar", ".cab", ".msi",
            ".ogv", ".flac", ".psd", ".exr", ".hdr", ".archive", ".pak", ".ucas", ".utoc", ".bundle"}
MAX_TEXT = 30 * 1024 * 1024
MAX_BIN = 64 * 1024 * 1024

# Profils de jeux connus : où sont les fichiers lisibles, quel wiki interroger.
# "packed" = données principales compressées (lire tout le jeu ne servirait à rien).
PROFILES = {
    "cyberpunk2077": {
        "title": "Cyberpunk 2077",
        "wiki": "cyberpunk.fandom.com",
        "packed": True,
        "text_dirs": [r"r6\config", r"r6\scripts", r"r6\tweaks",
                      r"bin\x64\plugins\cyber_engine_tweaks\mods"],
        "saves": [r"Saved Games\CD Projekt Red\Cyberpunk 2077"],
        "note": "Données dans archive\\pc\\content\\*.archive (compressées) et sauvegardes sav.dat (compressées) : "
                "illisibles directement, donc réponse tirée du wiki officiel du jeu.",
    },
}


def profile(name):
    n = _norm(name)
    for key, prof in PROFILES.items():
        if key in n or n in key and len(n) >= 6:
            return prof
    return None


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _match_library(exe, ctx):
    low = exe.lower().replace("/", "\\")
    # Le sélecteur de dossier de Windows (Tk) renvoie « D:/Jeux » : on normalise en « d:\\jeux »,
    # sinon un jeu installé dans un dossier perso n'était jamais reconnu.
    customs = [p.replace("/", "\\").lower().rstrip("\\") for p in ctx.config.get("game_folders", []) if p]
    for hint in customs + LIBRARY_HINTS:
        key = hint + "\\"
        idx = low.find(key)
        if idx >= 0:
            rest = exe[idx + len(key):].replace("/", "\\")
            game = rest.split("\\")[0]
            if game and "\\" in rest:
                return exe[:idx + len(key) + len(game)], game
    return None, None


def _anticheat(root, running):
    found = []
    try:
        names = {n.lower() for n in os.listdir(root)}
    except OSError:
        names = set()
    if "easyanticheat" in names or "easyanticheat_eos.exe" in running:
        found.append("EasyAntiCheat")
    if "battleye" in names or "beservice.exe" in running or "beservice_x64.exe" in running:
        found.append("BattlEye")
    if "vgc.exe" in running and "riot" in root.lower():
        found.append("Vanguard")
    return found


def _listdir(path):
    """os.listdir qui ne plante pas sur un dossier protégé ou disparu."""
    try:
        return os.listdir(path)
    except OSError:
        return []


def save_dirs(game):
    n = _norm(game)
    if len(n) < 3:
        return []
    home = os.path.expanduser("~")
    prof = profile(game)
    if prof and prof.get("saves"):
        known = [os.path.join(home, *p.split("\\")) for p in prof["saves"]
                 if os.path.isdir(os.path.join(home, *p.split("\\")))]
        if known:
            return known
    parents = [os.path.join(home, "Documents", "My Games"), os.path.join(home, "Saved Games"),
               os.path.join(home, "AppData", "Local"), os.path.join(home, "AppData", "Roaming"),
               os.path.join(home, "Documents")]
    locallow = os.path.join(home, "AppData", "LocalLow")
    if os.path.isdir(locallow):
        parents += [os.path.join(locallow, c) for c in _listdir(locallow)]
    out = []
    for parent in parents:
        if not os.path.isdir(parent):
            continue
        for child in _listdir(parent):
            cn = _norm(child)
            full = os.path.join(parent, child)
            if os.path.isdir(full) and cn and (n in cn or (len(cn) >= 5 and cn in n)):
                out.append(full)
    return out[:6]


def _running(ctx):
    import psutil
    procs, names = [], set()
    for p in psutil.process_iter(["name", "exe", "memory_info"]):
        try:
            name = (p.info.get("name") or "").lower()
            names.add(name)
            procs.append((name, p.info.get("exe") or "", p.info["memory_info"].rss if p.info.get("memory_info") else 0))
        except Exception:
            continue
    games = {}
    for name, exe, mem in procs:
        if not exe or name in IGNORE_EXE:
            continue
        root, game = _match_library(exe, ctx)
        if root and (root not in games or mem > games[root]["mem"]):
            games[root] = {"name": game, "exe": exe, "root": root, "mem": mem, "sure": True}
    if not games:  # repli : gros processus hors Windows qui n'est pas une app connue
        for name, exe, mem in procs:
            if (exe and name not in NOT_GAMES and name not in IGNORE_EXE and mem > 1.5 * 1024 ** 3
                    and "\\windows\\" not in exe.lower()):
                root = os.path.dirname(exe)
                games[root] = {"name": os.path.splitext(os.path.basename(exe))[0], "exe": exe,
                               "root": root, "mem": mem, "sure": False}
    return sorted(games.values(), key=lambda g: -g["mem"]), names


def installed_games(ctx):
    libs = []
    for steam in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, encoding="utf-8", errors="ignore") as f:
                for p in re.findall(r'"path"\s+"(.+?)"', f.read()):
                    libs.append(os.path.join(p.replace("\\\\", "\\"), "steamapps", "common"))
        except OSError:
            pass
    libs += [r"C:\Program Files\Epic Games", r"C:\Riot Games", r"C:\XboxGames",
             r"C:\Program Files (x86)\GOG Galaxy\Games", r"C:\Program Files\EA Games"]
    libs += ctx.config.get("game_folders", [])
    out = {}
    for lib in libs:
        if os.path.isdir(lib):
            for g in _listdir(lib):
                full = os.path.join(lib, g)
                if os.path.isdir(full):
                    out[full] = g
    return out


def _resolve(ctx, game):
    if game:
        n = _norm(game)
        for root, name in installed_games(ctx).items():
            if n and (n in _norm(name) or _norm(name) in n):
                return name, root
        if _LAST["name"] and n in _norm(_LAST["name"]):
            return _LAST["name"], _LAST["root"]
        raise ToolError(f"Je ne trouve pas le jeu « {game} » dans tes bibliothèques. "
                        "Ajoute son dossier dans game_folders (réglages ⚙).")
    if not _LAST["root"]:
        games, _ = _running(ctx)
        if games:
            _LAST.update(name=games[0]["name"], root=games[0]["root"])
    if not _LAST["root"]:
        raise ToolError("Aucun jeu lancé détecté. Dis-moi de quel jeu il s'agit.")
    return _LAST["name"], _LAST["root"]


@tool("detect_game", "Détecte le jeu vidéo actuellement lancé (nom, dossier d'installation, sauvegardes, anti-triche).",
      label="Je regarde à quoi tu joues")
def detect_game(ctx):
    games, names = _running(ctx)
    if not games:
        return "Aucun jeu détecté en cours d'exécution."
    g = games[0]
    _LAST.update(name=g["name"], root=g["root"])
    lines = [f"Jeu en cours : {g['name']}" + ("" if g["sure"] else " (probable)"),
             f"Exécutable : {g['exe']}", f"Dossier d'installation : {g['root']}"]
    saves = save_dirs(g["name"])
    if saves:
        lines.append("Sauvegardes / config probables : " + " ; ".join(saves))
    ac = _anticheat(g["root"], names)
    if ac:
        lines.append(f"Anti-triche : {', '.join(ac)} (Cronux lit seulement les fichiers sur disque)")
    if len(games) > 1:
        lines.append("Autres jeux ouverts : " + ", ".join(x["name"] for x in games[1:4]))
    return "\n".join(lines)


@tool("list_games", "Liste les jeux installés (Steam, Epic, Riot, Xbox, GOG, EA et dossiers perso).",
      label="Je liste tes jeux")
def list_games(ctx):
    games = installed_games(ctx)
    return "\n".join(f"- {n}" for n in sorted(games.values(), key=str.lower)) or "Aucun jeu trouvé."


def _variants(item):
    base = " ".join(item.lower().split())
    return list(dict.fromkeys(v for v in (base, base.replace(" ", "_"), base.replace(" ", ""),
                                          base.replace(" ", "-")) if len(v) >= 3))


def _patterns(variants):
    """Préparés une seule fois par recherche : une regex texte insensible à la casse, et les
    séquences d'octets à chercher dans les binaires (UTF-8 et UTF-16, en minuscules)."""
    text_re = re.compile("|".join(re.escape(v) for v in variants), re.I)
    needles = list(dict.fromkeys(v.lower().encode(enc) for v in variants for enc in ("utf-8", "utf-16-le")))
    return text_re, needles


CHUNK = 4 * 1024 * 1024


def _find_in_binary(path, needles):
    """Cherche dans un binaire par morceaux de 4 Mo (avant : fichier entier + copie en minuscules,
    jusqu'à 128 Mo de RAM par fichier). bytes.lower() + find() restent les opérations les plus
    rapides de Python pour ça (bien plus qu'une regex insensible à la casse)."""
    overlap = max(len(n) for n in needles) - 1
    with open(path, "rb") as fh:
        offset, tail = 0, b""
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                return None
            low = (tail + chunk).lower()
            hits = [p for p in (low.find(n) for n in needles) if p >= 0]
            if hits:
                pos = offset - len(tail) + min(hits)
                fh.seek(max(0, pos - 400))
                window = fh.read(800 + min(pos, 400))
                return _strings_around(window, min(pos, 400))
            tail = chunk[-overlap:] if overlap else b""
            offset += len(chunk)


def _strings_around(data, pos):
    win = data[max(0, pos - 400):pos + 400]
    parts = [s.decode("ascii") for s in re.findall(rb"[\x20-\x7e]{4,}", win)]
    parts += [s.decode("utf-16-le", "ignore") for s in re.findall(rb"(?:[\x20-\x7e]\x00){4,}", win)]
    return " | ".join(parts)[:350]


# ───────── Wiki (API MediaWiki des wikis Fandom) ─────────

SECTION_WORDS = ("acquisition", "location", "obtain", "how to get", "where to find", "obtaining", "loot",
                 "reward", "craft", "emplacement", "obtention", "où trouver", "walkthrough")


def _clean_wikitext(t):
    t = re.sub(r"(?s)<ref[^>]*?/>|<ref.*?</ref>|<!--.*?-->", "", t)
    for _ in range(4):  # modèles {{...}} imbriqués
        t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:File|Fichier|Image):[^\]]*\]\]", "", t)
    t = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", t)
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"<[^>]+>", " ", t)
    lines = [l.strip(" |!-*#:") for l in t.splitlines()]
    return "\n".join(l for l in lines if l and not l.startswith(("{|", "|}", "class=", "style=")))


def wiki_lookup(domain, item):
    """Cherche l'objet sur un wiki Fandom et renvoie les sections « où le trouver / comment l'obtenir »."""
    import requests
    api = f"https://{domain}/api.php"
    r = requests.get(api, params={"action": "query", "list": "search", "srsearch": item, "srlimit": 3,
                                  "format": "json"}, headers=UA, timeout=12)
    r.raise_for_status()
    titles = [h["title"] for h in r.json().get("query", {}).get("search", [])]
    if not titles:
        return None
    out = []
    for title in titles[:2]:
        r = requests.get(api, params={"action": "parse", "page": title, "prop": "wikitext", "redirects": 1,
                                      "format": "json"}, headers=UA, timeout=12)
        r.raise_for_status()
        raw = r.json().get("parse", {}).get("wikitext", {}).get("*", "")
        parts = re.split(r"(?m)^(==+)\s*(.*?)\s*\1\s*$", raw)
        intro, sections = parts[0], [(parts[i + 1], parts[i + 2]) for i in range(1, len(parts) - 2, 3)]
        picked = [f"## {h}\n{_clean_wikitext(b)[:1500]}" for h, b in sections
                  if any(w in h.lower() for w in SECTION_WORDS)]
        body = "\n".join(picked) if picked else _clean_wikitext(intro)[:1200]
        url = f"https://{domain}/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        out.append(f"### {title} ({url})\n{body}")
    return "\n\n".join(out)[:5000]


def _guide(ctx, game, item):
    prof = profile(game)
    if prof and prof.get("wiki"):
        try:
            res = wiki_lookup(prof["wiki"], item)
            if res:
                return f"Wiki {prof['title']} :\n{res}"
        except Exception:
            pass
    try:
        return "Recherche web :\n" + web_search(ctx, f"{game} {item} location where to find")
    except Exception as e:
        return f"(recherche en ligne impossible : {e})"


def _flatten(obj, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(v, f"{prefix}{k}.", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:20]):
            _flatten(v, f"{prefix}{i}.", out)
    elif obj not in (None, "", 0, False) and len(out) < 400:
        out[prefix[:-1]] = obj
    return out


INTEREST = ("quest", "mission", "location", "district", "level", "lifepath", "name", "difficulty",
            "playthrough", "playtime", "streetcred", "money", "chapter", "region", "zone", "map")


@tool("game_save_info", "Lit la sauvegarde la plus récente du jeu (fichiers lisibles seulement) pour savoir où en "
                        "est le joueur : niveau, quête suivie, temps de jeu…",
      {"game": {"type": "string", "description": "Optionnel : nom du jeu"}},
      label="Je regarde ta progression")
def game_save_info(ctx, game=None):
    name, _ = _resolve(ctx, game)
    folders = []
    for base in save_dirs(name):
        for dirpath, _, files in os.walk(base):
            if any(f.lower().endswith(".json") for f in files):
                folders.append(dirpath)
    if not folders:
        return f"Aucune sauvegarde lisible trouvée pour {name}."
    latest = max(folders, key=os.path.getmtime)
    facts = {}
    for f in os.listdir(latest):
        if f.lower().endswith(".json") and os.path.getsize(os.path.join(latest, f)) < 5 * 1024 * 1024:
            try:
                with open(os.path.join(latest, f), encoding="utf-8", errors="ignore") as fh:
                    facts.update(_flatten(json.load(fh)))
            except Exception:
                continue
    keep = {k: v for k, v in facts.items() if any(w in k.lower() for w in INTEREST)} or facts
    lines = [f"{k.split('.')[-1]} : {v}" for k, v in list(keep.items())[:40]]
    return f"Sauvegarde la plus récente : {os.path.basename(latest)}\n" + "\n".join(lines)


@tool("search_game_files",
      "Cherche un objet, PNJ, lieu ou quête dans les fichiers du jeu (données + sauvegardes) et renvoie "
      "les passages trouvés. Sans 'game', utilise le jeu en cours.",
      {"item": {"type": "string", "description": "Nom de l'objet (essaie aussi le nom anglais)"},
       "game": {"type": "string", "description": "Optionnel : nom du jeu"}},
      required=["item"], label="Je fouille les fichiers du jeu")
def search_game_files(ctx, item, game=None):
    name, root = _resolve(ctx, game)
    variants = _variants(item)
    if not variants:
        raise ToolError("Nom d'objet trop court.")
    prof = profile(name)
    if prof and prof.get("packed"):
        roots = [p for p in (os.path.join(root, *d.split("\\")) for d in prof.get("text_dirs", []))
                 if os.path.isdir(p)]
    else:
        roots = [root] + save_dirs(name)
    text_re, needles = _patterns(variants)
    hits, scanned, skipped, deadline = [], 0, 0, time.time() + 45
    timed_out = False
    for base in roots:
        for dirpath, dirnames, files in os.walk(base):
            dirnames[:] = [d for d in dirnames if d.lower() not in ("easyanticheat", "battleye", "redist", "_commonredist")]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in SKIP_EXT:
                    continue
                path = os.path.join(dirpath, f)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                try:
                    if ext in TEXT_EXT and size <= MAX_TEXT:
                        scanned += 1
                        n = 0
                        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                            for ln, line in enumerate(fh, 1):
                                if text_re.search(line):
                                    hits.append(f"{os.path.relpath(path, base)} (ligne {ln}) : {line.strip()[:220]}")
                                    n += 1
                                    if n >= 4:
                                        break
                    elif size <= MAX_BIN:
                        scanned += 1
                        found = _find_in_binary(path, needles)
                        if found is not None:
                            hits.append(f"{os.path.relpath(path, base)} (binaire) : {found}")
                    else:
                        skipped += 1
                except (OSError, ValueError):
                    continue
                if time.time() > deadline:
                    timed_out = True
                if len(hits) >= 30 or timed_out:
                    break
            if len(hits) >= 30 or timed_out:
                break
        if len(hits) >= 30 or timed_out:
            break  # avant, la recherche repartait sur le dossier suivant même après le délai
    head = (f"Recherche de « {item} » dans {name} : {scanned} fichiers lisibles lus"
            + (f", {skipped} archives trop grosses ignorées" if skipped else "")
            + (" (temps limite atteint)" if timed_out else ""))
    parts = [head]
    if prof and prof.get("note"):
        parts.append(prof["note"])
    parts.append("\n".join(hits) if hits else "Rien trouvé dans les fichiers lisibles.")
    if len(hits) < 3 or (prof and prof.get("packed")):
        parts.append(_guide(ctx, prof["title"] if prof else name, item))
    return "\n".join(parts)


@tool("read_game_file", "Lit un passage d'un fichier de jeu (chemin complet) autour d'un mot ou d'une ligne.",
      {"path": {"type": "string"}, "query": {"type": "string"}, "line": {"type": "integer"}},
      required=["path"], label="Je lis le fichier du jeu")
def read_game_file(ctx, path, query=None, line=None):
    if not os.path.isfile(path):
        name, root = _resolve(ctx, None)
        candidate = os.path.join(root, path)
        if not os.path.isfile(candidate):
            raise ToolError(f"Fichier introuvable : {path}")
        path = candidate
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
        center = int(line) if line else None
        if query and not center:
            q = query.lower()
            center = next((i + 1 for i, l in enumerate(lines) if q in l.lower()), None)
        center = center or 1
        start = max(0, center - 25)
        return "".join(f"{i + 1}: {l}" for i, l in enumerate(lines[start:start + 50], start))[:6000]
    if query:
        found = _find_in_binary(path, _patterns([query])[1])
        return found if found is not None else "Mot non trouvé dans ce fichier."
    with open(path, "rb") as fh:
        data = fh.read(200000)
    return " | ".join(s.decode("ascii") for s in re.findall(rb"[\x20-\x7e]{6,}", data))[:5000]
