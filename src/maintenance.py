"""Entretien du PC : espace disque, nettoyage de caches sûrs, détection des jeux peu joués.

Principe de sécurité : Cronux ne supprime QUE des dossiers de cache/temporaires connus et sans risque
(fichiers recréés automatiquement). Jamais tes documents. Toute suppression demande confirmation.
Pour désinstaller un jeu, Cronux lance le désinstalleur officiel — il ne supprime pas les dossiers à la main."""
import ctypes
import os
import shutil
import string
import time

from tools import IS_WIN, ToolError, _open, tool

GB = 1024 ** 3
MB = 1024 ** 2


def _env(name):
    return os.environ.get(name, "")


def cache_targets():
    """Liste des caches sûrs à nettoyer : (clé, libellé, chemin, 'contenu' ou 'corbeille')."""
    local = _env("LOCALAPPDATA")
    appdata = _env("APPDATA")
    home = os.path.expanduser("~")
    t = [
        ("temp_user", "Fichiers temporaires (utilisateur)", _env("TEMP"), "contenu"),
        ("temp_win", "Fichiers temporaires (Windows)", r"C:\Windows\Temp", "contenu"),
        ("chrome", "Cache Chrome", os.path.join(local, r"Google\Chrome\User Data\Default\Cache"), "contenu"),
        ("edge", "Cache Edge", os.path.join(local, r"Microsoft\Edge\User Data\Default\Cache"), "contenu"),
        ("pip", "Cache pip (Python)", os.path.join(local, r"pip\Cache"), "contenu"),
        ("npm", "Cache npm", os.path.join(appdata, "npm-cache"), "contenu"),
        ("crashdumps", "Rapports de plantage", os.path.join(local, r"CrashDumps"), "contenu"),
        ("corbeille", "Corbeille", None, "corbeille"),
    ]
    # Profils Firefox (cache2)
    ff = os.path.join(appdata, r"Mozilla\Firefox\Profiles")
    if os.path.isdir(ff):
        for prof in os.listdir(ff):
            c = os.path.join(ff, prof, "cache2")
            if os.path.isdir(c):
                t.append((f"ff_{prof}", "Cache Firefox", c, "contenu"))
    return [(k, lbl, p, kind) for k, lbl, p, kind in t if kind == "corbeille" or (p and os.path.isdir(p))]


def _dir_size(path, deadline):
    total = 0
    for dirpath, dirnames, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
        if time.time() > deadline:
            return total, True
    return total, False


def _recycle_size():
    if not IS_WIN:
        return 0
    try:
        SHQUERYRBINFO = ctypes.c_uint64 * 3  # cbSize, i64Size, i64NumItems (approx layout)

        class RBINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_uint64),
                        ("i64NumItems", ctypes.c_uint64)]
        info = RBINFO()
        info.cbSize = ctypes.sizeof(RBINFO)
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            return int(info.i64Size)
    except Exception:
        pass
    return 0


def empty_recycle_bin():
    if not IS_WIN:
        return False
    try:
        # 0x7 = pas de confirmation + pas de son + pas de progression
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
        return True
    except Exception:
        return False


def _clear_contents(path):
    """Supprime le CONTENU d'un dossier (pas le dossier lui-même). Ignore les fichiers verrouillés."""
    freed = 0
    for entry in os.scandir(path):
        try:
            if entry.is_file() or entry.is_symlink():
                size = entry.stat(follow_symlinks=False).st_size
                os.remove(entry.path)
                freed += size
            elif entry.is_dir():
                size, _ = _dir_size(entry.path, time.time() + 5)
                shutil.rmtree(entry.path, ignore_errors=True)
                if not os.path.exists(entry.path):
                    freed += size
        except (OSError, PermissionError):
            continue  # fichier en cours d'utilisation : on laisse
    return freed


def analyze(deadline_each=6):
    """Renvoie l'espace disque et la taille de chaque cache nettoyable."""
    drives = []
    if IS_WIN:
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.isdir(root):
                try:
                    u = shutil.disk_usage(root)
                    drives.append({"drive": root, "total": u.total, "free": u.free, "used": u.used})
                except OSError:
                    pass
    else:
        u = shutil.disk_usage(os.path.expanduser("~"))
        drives.append({"drive": "~", "total": u.total, "free": u.free, "used": u.used})

    caches = []
    for key, label, path, kind in cache_targets():
        if kind == "corbeille":
            caches.append({"key": key, "label": label, "size": _recycle_size(), "kind": kind})
        else:
            size, capped = _dir_size(path, time.time() + deadline_each)
            caches.append({"key": key, "label": label, "size": size, "path": path,
                           "kind": kind, "approx": capped})
    return {"drives": drives, "caches": caches}


def clean(keys):
    """Nettoie les caches dont la clé est dans `keys`. Renvoie (octets_libérés, détails)."""
    freed, details = 0, []
    by_key = {k: (lbl, p, kind) for k, lbl, p, kind in cache_targets()}
    for key in keys:
        if key not in by_key:
            continue
        label, path, kind = by_key[key]
        if kind == "corbeille":
            before = _recycle_size()
            if empty_recycle_bin():
                freed += before
                details.append(f"{label} : vidée")
        else:
            got = _clear_contents(path)
            freed += got
            details.append(f"{label} : {got / MB:.0f} Mo")
    return freed, details


# ───────── Jeux peu joués ─────────

def _last_used(game_name, root):
    """Estime la dernière utilisation d'un jeu (fichier le plus récent côté sauvegardes, sinon dossier)."""
    import games
    newest = 0
    for base in games.save_dirs(game_name) or []:
        for dirpath, _, files in os.walk(base):
            for f in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(dirpath, f)))
                except OSError:
                    pass
    try:
        newest = max(newest, os.path.getmtime(root))
    except OSError:
        pass
    return newest


def unused_games(ctx, days=45, deadline=20):
    """Liste les jeux installés non utilisés depuis `days` jours, avec leur taille."""
    import games
    installed = games.installed_games(ctx)
    now, cutoff = time.time(), days * 86400
    out, stop = [], time.time() + deadline
    for root, name in installed.items():
        last = _last_used(name, root)
        inactive_days = int((now - last) / 86400) if last else None
        size, _ = _dir_size(root, min(stop, time.time() + 4))
        out.append({"name": name, "root": root, "size": size,
                    "inactive_days": inactive_days, "last": last})
        if time.time() > stop:
            break
    unused = [g for g in out if g["inactive_days"] is None or g["inactive_days"] >= days]
    unused.sort(key=lambda g: -g["size"])
    return unused


def _steam_appid(root):
    """Retrouve l'appid Steam d'un jeu à partir des manifestes, pour une désinstallation propre."""
    common = os.path.dirname(root)              # ...\steamapps\common
    steamapps = os.path.dirname(common)         # ...\steamapps
    folder = os.path.basename(root)
    if os.path.basename(steamapps).lower() != "steamapps":
        return None
    import re
    for f in os.listdir(steamapps):
        if f.startswith("appmanifest_") and f.endswith(".acf"):
            try:
                txt = open(os.path.join(steamapps, f), encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if re.search(r'"installdir"\s*"' + re.escape(folder) + '"', txt, re.I):
                m = re.search(r'"appid"\s*"(\d+)"', txt, re.I)
                if m:
                    return m.group(1)
    return None


def uninstall_game(root):
    """Lance la désinstallation OFFICIELLE (Steam ou désinstalleur du jeu). Ne supprime rien à la main."""
    appid = _steam_appid(root)
    if appid:
        _open(f"steam://uninstall/{appid}")
        return "Fenêtre de désinstallation Steam ouverte."
    for f in os.listdir(root):
        low = f.lower()
        if low.startswith(("unins", "uninstall")) and low.endswith(".exe"):
            _open(os.path.join(root, f))
            return "Désinstalleur du jeu lancé."
    if IS_WIN:
        _open("ms-settings:appsfeatures")
        return "Ouvre « Applications installées » pour désinstaller ce jeu."
    raise ToolError("Aucun désinstalleur trouvé.")


# ───────── Outils exposés à l'IA ─────────

def _fmt(n):
    return f"{n / GB:.1f} Go" if n >= GB else f"{n / MB:.0f} Mo"


@tool("disk_report", "Analyse l'espace disque et la taille des fichiers temporaires/caches nettoyables.",
      label="J'analyse l'espace disque")
def disk_report(ctx):
    data = analyze()
    lines = []
    for d in data["drives"]:
        pct = d["free"] * 100 // d["total"] if d["total"] else 0
        lines.append(f"Disque {d['drive']} : {_fmt(d['free'])} libres sur {_fmt(d['total'])} ({pct} % libre)")
    total_cache = sum(c["size"] for c in data["caches"])
    lines.append(f"\nÀ nettoyer (sûr) : {_fmt(total_cache)} au total")
    for c in sorted(data["caches"], key=lambda c: -c["size"]):
        if c["size"] > MB:
            lines.append(f"- {c['label']} : {_fmt(c['size'])}{' ~' if c.get('approx') else ''}")
    lines.append("\nDis « nettoie » pour libérer cet espace (je demande confirmation), "
                 "ou ouvre le bouton 🧹 pour choisir.")
    return "\n".join(lines)


@tool("clean_cache", "Nettoie les fichiers temporaires et caches sûrs pour libérer de l'espace (avec confirmation).",
      label="Je nettoie le cache")
def clean_cache(ctx):
    data = analyze()
    keys = [c["key"] for c in data["caches"] if c["size"] > 0]
    total = sum(c["size"] for c in data["caches"])
    if total < MB:
        return "Rien à nettoyer, c'est déjà propre."
    if not ctx.ask("Nettoyer le cache ?", f"Cronux va libérer environ {_fmt(total)} "
                                           "(fichiers temporaires, caches navigateur, corbeille). Continuer ?"):
        return "Nettoyage annulé."
    freed, details = clean(keys)
    return f"Nettoyage terminé : {_fmt(freed)} libérés.\n" + "\n".join(details)


@tool("unused_games", "Repère les jeux installés auxquels tu ne joues plus et propose de les désinstaller.",
      {"days": {"type": "integer", "description": "Seuil d'inactivité en jours (défaut 45)"}},
      label="Je cherche les jeux oubliés")
def unused_games_tool(ctx, days=45):
    games_list = unused_games(ctx, days=int(days or 45))
    if not games_list:
        return f"Aucun jeu inactif depuis plus de {days} jours. Rien à récupérer de ce côté."
    lines = [f"Jeux non joués depuis {days}+ jours :"]
    for g in games_list[:12]:
        when = f"{g['inactive_days']} j sans y jouer" if g["inactive_days"] is not None else "jamais vu lancé"
        lines.append(f"- {g['name']} — {_fmt(g['size'])} — {when}")
    lines.append("\nDis-moi lequel désinstaller (j'ouvre le désinstalleur officiel), ou ouvre le bouton 🧹.")
    return "\n".join(lines)


@tool("uninstall_game", "Ouvre la désinstallation officielle d'un jeu (Steam ou désinstalleur du jeu).",
      {"name": {"type": "string", "description": "Nom du jeu à désinstaller"}},
      required=["name"], label="J'ouvre la désinstallation")
def uninstall_game_tool(ctx, name):
    import games
    installed = games.installed_games(ctx)
    n = games._norm(name)
    match = next((root for root, gn in installed.items() if n in games._norm(gn) or games._norm(gn) in n), None)
    if not match:
        raise ToolError(f"Jeu « {name} » introuvable dans tes bibliothèques.")
    if not ctx.ask("Désinstaller ce jeu ?", f"Ouvrir la désinstallation de « {name} » ?"):
        return "Désinstallation annulée."
    return uninstall_game(match)
