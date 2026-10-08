#!/usr/bin/env pythonw
# -*- coding: utf-8 -*-
"""Cronux — assistant IA local pour Windows. CRONUX_BUNDLE (fichier unique auto-extractible).
Double-clique ce fichier pour lancer Cronux. Pour mettre à jour : remplace ce fichier par le neuf."""
import base64
import os
import sys
import subprocess

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Cronux")
CODE_DIR = os.path.join(APP_DIR, "app")

# ------------------------------------------------------------------ modules embarqués
FILES = {}  # @@FILES@@

ICON_B64 = ""  # @@ICON@@
DEPS = [("customtkinter", "customtkinter>=5.2"), ("requests", "requests>=2.31"),
        ("spotipy", "spotipy>=2.24"), ("psutil", "psutil>=5.9"), ("PIL", "pillow>=10.0")]
if sys.platform == "win32":
    DEPS.append(("win32com", "pywin32>=306"))


def _write_if_changed(path, data):
    """N'écrit que si le contenu a changé (évite de réécrire ~15 fichiers à chaque lancement)."""
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)  # jamais de module à moitié écrit si le PC s'éteint pendant l'extraction


def extract():
    os.makedirs(CODE_DIR, exist_ok=True)
    for name, b64 in FILES.items():
        _write_if_changed(os.path.join(CODE_DIR, name), base64.b64decode(b64))
    _write_if_changed(os.path.join(CODE_DIR, "cronux.ico"), base64.b64decode(ICON_B64))


def missing_deps():
    # find_spec vérifie la présence d'un module SANS l'importer : avant, customtkinter, spotipy,
    # Pillow, pywin32… étaient tous chargés à chaque démarrage juste pour ce test.
    import importlib.util
    miss = []
    for mod, pipname in DEPS:
        try:
            found = importlib.util.find_spec(mod) is not None
        except Exception:
            found = False
        if not found:
            miss.append(pipname)
    return miss


def install(deps):
    # Petite fenêtre d'attente (tkinter est toujours présent)
    splash = None
    try:
        import tkinter as tk
        splash = tk.Tk()
        splash.title("Cronux")
        splash.geometry("360x120")
        tk.Label(splash, text="Première installation de Cronux…\n(une minute, une seule fois)",
                 font=("Segoe UI", 11)).pack(expand=True)
        splash.update()
    except Exception:
        splash = None
    try:
        base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q"]
        flags = 0x08000000 if sys.platform == "win32" else 0  # pas de fenêtre console
        try:
            res = subprocess.run(base + list(deps), check=False, creationflags=flags)
            if res.returncode != 0:
                # Python installé « pour tous les utilisateurs » : pas le droit d'écrire → installation perso
                subprocess.run(base + ["--user"] + list(deps), check=False, creationflags=flags)
        except OSError:
            pass
    finally:
        if splash is not None:
            try:
                splash.destroy()
            except Exception:
                pass


def _show_error(message):
    """Affiche l'erreur dans une fenêtre : avec pythonw, une erreur au démarrage était invisible."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Cronux", message, parent=root)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def main():
    extract()
    if os.environ.get("CRONUX_EXTRACT_ONLY") == "1":
        return
    deps = missing_deps()
    if deps:
        install(deps)
        importlib_invalidate()
        still = missing_deps()
        if still:
            _show_error("Cronux n'a pas pu installer : " + ", ".join(still) + ".\n\n"
                        "Vérifie ta connexion Internet, puis relance Cronux. Sinon, ouvre un terminal et tape :\n"
                        f"py -m pip install {' '.join(still)}")
            return
    sys.path.insert(0, CODE_DIR)
    os.environ["CRONUX_SELF"] = os.path.abspath(__file__)
    try:
        import main as cronux_main
        app = cronux_main.App()
    except Exception as e:
        import traceback
        log = os.path.join(APP_DIR, "erreur_demarrage.txt")
        try:
            with open(log, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except OSError:
            pass
        _show_error(f"Cronux n'a pas pu démarrer :\n{type(e).__name__}: {e}\n\nDétails : {log}")
        return
    app.mainloop()


def importlib_invalidate():
    import importlib
    importlib.invalidate_caches()  # pour voir les paquets que pip vient d'installer
    import site
    try:
        user_site = site.getusersitepackages()
        if os.path.isdir(user_site) and user_site not in sys.path:
            sys.path.append(user_site)  # installation « --user » faite pendant ce lancement
    except Exception:
        pass


if __name__ == "__main__":
    main()
