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


def extract():
    os.makedirs(CODE_DIR, exist_ok=True)
    for name, b64 in FILES.items():
        data = base64.b64decode(b64)
        path = os.path.join(CODE_DIR, name)
        try:
            if os.path.exists(path) and open(path, "rb").read() == data:
                continue
        except OSError:
            pass
        with open(path, "wb") as f:
            f.write(data)
    with open(os.path.join(CODE_DIR, "cronux.ico"), "wb") as f:
        f.write(base64.b64decode(ICON_B64))


def missing_deps():
    import importlib
    miss = []
    for mod, pipname in DEPS:
        try:
            importlib.import_module(mod)
        except Exception:
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
        subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", *deps],
                       check=False)
    finally:
        if splash is not None:
            try:
                splash.destroy()
            except Exception:
                pass


def main():
    extract()
    if os.environ.get("CRONUX_EXTRACT_ONLY") == "1":
        return
    deps = missing_deps()
    if deps:
        install(deps)
    sys.path.insert(0, CODE_DIR)
    os.environ["CRONUX_SELF"] = os.path.abspath(__file__)
    import main as cronux_main
    cronux_main.App().mainloop()


if __name__ == "__main__":
    main()
