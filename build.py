"""Construit le fichier unique Cronux.pyw (auto-extractible) à partir de src/ et launcher.py.

Usage : python build.py [chemin_sortie]   (défaut : dist/Cronux.pyw)"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")


def build(out_path):
    files = {}
    for name in sorted(os.listdir(SRC)):
        if name.endswith(".py"):
            with open(os.path.join(SRC, name), "rb") as f:
                files[name] = base64.b64encode(f.read()).decode("ascii")
    with open(os.path.join(SRC, "cronux.ico"), "rb") as f:
        icon = base64.b64encode(f.read()).decode("ascii")
    with open(os.path.join(HERE, "launcher.py"), encoding="utf-8") as f:
        launcher = f.read()
    for marker in ("FILES = {}  # @@FILES@@", 'ICON_B64 = ""  # @@ICON@@'):
        if marker not in launcher:
            raise SystemExit(f"Marqueur absent de launcher.py : {marker}")
    launcher = launcher.replace("FILES = {}  # @@FILES@@", f"FILES = {files!r}")
    launcher = launcher.replace('ICON_B64 = ""  # @@ICON@@', f"ICON_B64 = {icon!r}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(launcher)
    return out_path


if __name__ == "__main__":
    out = build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "dist", "Cronux.pyw"))
    print(f"Bundle écrit : {out} ({os.path.getsize(out) // 1024} Ko)")
