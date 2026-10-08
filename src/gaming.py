"""Mode Gaming (fermer/relancer les apps gourmandes) et capture d'écran + partage Discord."""
import datetime
import os
import subprocess
import sys

from config import APP_DIR
from tools import IS_WIN, ToolError, _open, tool

# Apps non essentielles, souvent gourmandes, qu'on peut fermer avant de jouer.
DEFAULT_CLOSE = ["chrome", "msedge", "firefox", "opera", "brave", "slack", "teams", "ms-teams",
                 "onedrive", "dropbox", "spotify", "steamwebhelper", "epicgameslauncher",
                 "razer synapse", "logioptionsplus", "adobe", "ccleaner"]
# Jamais fermer ça.
NEVER_CLOSE = {"explorer.exe", "cronux.exe", "cronux-update.exe", "python.exe", "pythonw.exe",
               "ollama.exe", "ollama_llama_server.exe", "discord.exe", "steam.exe", "dwm.exe",
               "csrss.exe", "winlogon.exe", "services.exe", "lsass.exe", "system"}
CLOSED_FILE = os.path.join(APP_DIR, "gaming_closed.txt")
NOWIN = 0x08000000 if IS_WIN else 0


def _close_list(ctx):
    extra = [x.lower() for x in ctx.config.get("gaming_close", [])]
    return list(dict.fromkeys(DEFAULT_CLOSE + extra))


def gaming_on(ctx):
    """Ferme les apps gourmandes en arrière-plan. Retient ce qui a été fermé pour le relancer après."""
    import psutil
    targets = _close_list(ctx)
    closed, paths = [], {}
    for p in psutil.process_iter(["name", "exe"]):
        try:
            name = (p.info.get("name") or "").lower()
            if name in NEVER_CLOSE or not name:
                continue
            base = name[:-4] if name.endswith(".exe") else name
            if any(t in base for t in targets):
                exe = p.info.get("exe")
                if exe:
                    paths[name] = exe
                p.terminate()
                closed.append(name)
        except Exception:
            continue
    closed = sorted(set(closed))
    if paths:
        try:
            with open(CLOSED_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(set(paths.values()))))
        except OSError:
            pass
    if not closed:
        return "Rien à fermer, ton PC est déjà léger. Bon jeu !"
    return f"Mode Gaming activé : {len(closed)} app(s) fermée(s) — {', '.join(closed)}. Bon jeu !"


def gaming_off(ctx):
    """Relance ce qui avait été fermé par le Mode Gaming."""
    if not os.path.exists(CLOSED_FILE):
        return "Rien à relancer."
    try:
        paths = [l.strip() for l in open(CLOSED_FILE, encoding="utf-8").read().splitlines() if l.strip()]
    except OSError:
        return "Rien à relancer."
    relaunched = 0
    for exe in paths:
        if os.path.exists(exe):
            try:
                _open(exe)
                relaunched += 1
            except Exception:
                pass
    try:
        os.remove(CLOSED_FILE)
    except OSError:
        pass
    return f"Mode Gaming désactivé : {relaunched} app(s) relancée(s)."


@tool("gaming_mode", "Active ou désactive le Mode Gaming : ferme les apps gourmandes avant de jouer (on) "
                     "puis les relance (off), pour gagner en performances.",
      {"state": {"type": "string", "enum": ["on", "off"]}},
      required=["state"], label="Mode Gaming")
def gaming_mode(ctx, state):
    if not IS_WIN:
        return "Disponible sous Windows."
    if state == "on":
        if not ctx.ask("Activer le Mode Gaming ?", "Cronux va fermer les apps gourmandes en arrière-plan "
                                                   "(navigateurs, Spotify, Teams…) pour libérer des ressources. "
                                                   "Tu pourras les relancer avec « mode gaming off »."):
            return "Mode Gaming annulé."
        return gaming_on(ctx)
    return gaming_off(ctx)


# ───────── Capture d'écran + partage Discord ─────────

def take_screenshot(region=None):
    """Capture l'écran (ou une région) et renvoie le chemin du PNG enregistré."""
    try:
        from PIL import ImageGrab
    except ImportError:
        raise ToolError("Le module Pillow manque (capture d'écran indisponible).")
    img = ImageGrab.grab(bbox=region)
    folder = os.path.join(os.path.expanduser("~"), "Pictures", "Cronux")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"capture_{datetime.datetime.now():%Y%m%d_%H%M%S}.png")
    img.save(path)
    return path


@tool("screenshot", "Prend une capture d'écran et l'enregistre (dossier Images/Cronux).",
      label="Je prends une capture")
def screenshot(ctx):
    if not IS_WIN:
        return "Disponible sous Windows."
    path = take_screenshot()
    _open(os.path.dirname(path))
    return f"Capture enregistrée : {path}"


@tool("screenshot_to_discord", "Prend une capture d'écran et l'envoie dans un salon Discord (via le bot).",
      {"channel": {"type": "string", "description": "Salon, ex. 'général' ou 'serveur/salon'"},
       "message": {"type": "string", "description": "Légende optionnelle"}},
      required=["channel"], label="Je capture et j'envoie sur Discord")
def screenshot_to_discord(ctx, channel, message=""):
    if not IS_WIN:
        return "Disponible sous Windows."
    import discord_tools
    path = take_screenshot()
    if not ctx.ask("Envoyer la capture sur Discord ?", f"Salon : {channel}\nFichier : {os.path.basename(path)}"):
        return f"Envoi annulé. La capture reste ici : {path}"
    return discord_tools.send_file(ctx, channel, path, message)
