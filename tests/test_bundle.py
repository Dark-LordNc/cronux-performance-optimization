"""Construction du Cronux.pyw unique et extraction par le lanceur."""
import base64
import importlib.machinery
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

import build  # noqa: E402


def _load_launcher(path, appdata, monkeypatch):
    monkeypatch.setenv("APPDATA", str(appdata))
    loader = importlib.machinery.SourceFileLoader("cronux_bundle", path)  # .pyw : chargeur explicite
    spec = importlib.util.spec_from_loader("cronux_bundle", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bundle_roundtrip(tmp_path, monkeypatch):
    out = build.build(str(tmp_path / "Cronux.pyw"))
    text = open(out, encoding="utf-8").read()
    assert "CRONUX_BUNDLE" in text  # marqueur vérifié par le bouton « mise à jour »
    compile(text, out, "exec")
    env = dict(os.environ, APPDATA=str(tmp_path / "appdata"), CRONUX_EXTRACT_ONLY="1")
    subprocess.run([sys.executable, out], env=env, check=True, timeout=60)
    app = tmp_path / "appdata" / "Cronux" / "app"
    src = os.path.join(ROOT, "src")
    for name in os.listdir(src):
        if name.endswith((".py", ".ico")):
            with open(os.path.join(src, name), "rb") as a, open(app / name, "rb") as b:
                assert a.read() == b.read(), name


def test_extract_skips_unchanged_files(tmp_path, monkeypatch):
    out = build.build(str(tmp_path / "Cronux.pyw"))
    mod = _load_launcher(out, tmp_path / "ad", monkeypatch)
    mod.extract()
    target = os.path.join(mod.CODE_DIR, "main.py")
    os.utime(target, ns=(1, 1))
    mod.extract()
    assert os.stat(target).st_mtime_ns == 1          # identique : pas réécrit
    with open(target, "a", encoding="utf-8") as f:
        f.write("# modifié\n")
    mod.extract()
    assert open(target, "rb").read() == base64.b64decode(mod.FILES["main.py"])  # remis d'aplomb
    assert not [f for f in os.listdir(mod.CODE_DIR) if f.endswith(".tmp")]


def test_missing_deps_does_not_import(tmp_path, monkeypatch):
    out = build.build(str(tmp_path / "Cronux.pyw"))
    mod = _load_launcher(out, tmp_path / "ad", monkeypatch)
    monkeypatch.setattr(mod, "DEPS", [("json", "json"), ("module_qui_nexiste_pas_xyz", "paquet-xyz")])
    sys.modules.pop("spotipy", None)
    assert mod.missing_deps() == ["paquet-xyz"]


def test_launcher_reports_missing_deps(tmp_path, monkeypatch):
    out = build.build(str(tmp_path / "Cronux.pyw"))
    mod = _load_launcher(out, tmp_path / "ad", monkeypatch)
    shown, installed = [], []
    monkeypatch.setattr(mod, "DEPS", [("module_qui_nexiste_pas_xyz", "paquet-xyz")])
    monkeypatch.setattr(mod, "install", installed.append)
    monkeypatch.setattr(mod, "_show_error", shown.append)
    monkeypatch.delenv("CRONUX_EXTRACT_ONLY", raising=False)
    mod.main()
    assert installed == [["paquet-xyz"]] and "paquet-xyz" in shown[0]
