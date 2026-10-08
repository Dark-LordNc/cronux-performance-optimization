"""Outils : exécution, fichiers, Outlook (ids), Spotify, matériel, jeux, entretien, Mode Gaming, Discord."""
import os
import threading
import time
import urllib.request

import pytest

import config
import discord_auth
import discord_tools
import games
import gaming
import hardware
import maintenance
import tools


# ───────── tools.run ─────────

def test_run_unknown_tool(ctx):
    assert tools.run("nope", {}, ctx) == "Erreur : outil inconnu 'nope'."


def test_run_drops_invented_args_and_reports_missing(ctx):
    out = tools.run("get_datetime", {"timezone": "Europe/Paris"}, ctx)
    assert out.startswith("Nous sommes le")
    assert "manquant(s) : query" in tools.run("search_files", {}, ctx)
    assert tools.run("search_files", "pas un dict", ctx).startswith("Erreur d'arguments")


def test_run_internal_typeerror_is_not_an_argument_error(ctx, monkeypatch):
    def broken(ctx):
        return None + 1
    monkeypatch.setitem(tools.REGISTRY["get_datetime"], "fn", broken)
    assert tools.run("get_datetime", {}, ctx).startswith("Erreur pendant get_datetime : TypeError")


def test_run_serializes_non_string(ctx, monkeypatch):
    monkeypatch.setitem(tools.REGISTRY["get_datetime"], "fn", lambda ctx: {"a": "é"})
    assert tools.run("get_datetime", {}, ctx) == '{"a": "é"}'


def test_every_tool_schema_matches_its_function():
    import inspect
    import agent  # noqa: F401  (enregistre tous les outils)
    assert len(tools.REGISTRY) >= 35
    for name, t in tools.REGISTRY.items():
        params = inspect.signature(t["fn"]).parameters
        props = t["schema"]["function"]["parameters"]["properties"]
        assert set(props) <= set(params), name
        for req in t["schema"]["function"]["parameters"]["required"]:
            assert req in params and params[req].default is inspect.Parameter.empty, (name, req)


# ───────── search_files ─────────

@pytest.fixture
def tree(tmp_path):
    for rel in ["Docs/Facture EDF mars.pdf", "Docs/facture edf avril.PDF", "Docs/edf/notes.txt",
                "Docs/node_modules/facture edf.pdf", "Docs/.cache/facture edf.pdf", "Autre/Facture EDF/x.txt"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    return tmp_path


def test_search_files(tree, ctx):
    ctx.config["search_folders"] = [str(tree / "Docs"), str(tree / "Autre")]
    out = tools.search_files(ctx, "facture edf", "pdf")
    assert out.startswith("2 résultat(s)") and "node_modules" not in out and ".cache" not in out
    out = tools.search_files(ctx, "facture edf")
    assert out.startswith("3 résultat(s)") and "[dossier]" in out
    assert "Aucun fichier" in tools.search_files(ctx, "introuvable")
    with pytest.raises(tools.ToolError):
        tools.search_files(ctx, "   ")


def test_search_files_deadline_applies_to_all_roots(tree, ctx, monkeypatch):
    ctx.config["search_folders"] = [str(tree / "Docs"), str(tree / "Autre")]
    walked = []
    real_walk = os.walk
    monkeypatch.setattr(tools.os, "walk", lambda root: walked.append(root) or real_walk(root))
    clock = iter([0, 100, 100, 100, 100, 100, 100])
    monkeypatch.setattr(tools.time, "time", lambda: next(clock))
    tools.search_files(ctx, "facture")
    assert walked == [str(tree / "Docs")]  # avant : le 2e dossier était parcouru malgré le délai dépassé


# ───────── applications, mails, Spotify ─────────

def test_shortcuts_are_cached(monkeypatch):
    scans = []
    monkeypatch.setattr(tools, "_scan_shortcuts", lambda: scans.append(1) or [("Spotify", "s.lnk")])
    for _ in range(5):
        assert tools._start_menu_shortcuts() == [("Spotify", "s.lnk")]
    assert len(scans) == 1
    tools._SHORTCUTS["time"] -= tools.SHORTCUTS_TTL + 1
    tools._start_menu_shortcuts()
    assert len(scans) == 2


def test_launch_app_picks_best_shortcut(monkeypatch, ctx):
    opened = []
    monkeypatch.setattr(tools, "_open", opened.append)
    monkeypatch.setattr(tools, "_scan_shortcuts", lambda: [
        ("Désinstaller Spotify", "u.lnk"), ("Spotify Web Helper", "w.lnk"), ("Spotify", "s.lnk")])
    assert tools.launch_app(ctx, "spotify") == "spotify lancé."  # alias spotify: d'abord
    assert opened == ["spotify:"]
    assert tools.launch_app(ctx, "Spot") == "Spotify lancé."
    assert opened[-1] == "s.lnk"


def test_mail_ids_are_stable_and_bounded(monkeypatch):
    assert tools._mail_id("A") == 1 and tools._mail_id("B") == 2 and tools._mail_id("A") == 1
    monkeypatch.setattr(tools, "MAX_MAIL_IDS", 3)
    for e in "CDE":
        tools._mail_id(e)
    assert sorted(tools._MAIL_CACHE) == [3, 4, 5] and "A" not in tools._MAIL_IDS
    assert tools._mail_id("F") == 6


class FakeSpotify:
    def __init__(self):
        self.device_calls = 0
        self.played = []
        self.fail_once = False

    def devices(self):
        self.device_calls += 1
        return {"devices": [{"id": "phone", "type": "Smartphone"}, {"id": "pc", "type": "Computer"}]}

    def start_playback(self, device_id=None, **kw):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("Device not found")
        self.played.append(device_id)

    def volume(self, v, device_id=None):
        self.played.append((v, device_id))

    def search(self, q, type, limit):
        return {type + "s": {"items": [{"uri": "u", "name": "Titre", "artists": [{"name": "Art"}]}]}}


def test_spotify_device_cache_and_retry(ctx, monkeypatch):
    sp = FakeSpotify()
    ctx.config["spotify_client_id"] = "cid"
    tools._SP.update(client=sp, cid="cid", device=None, device_time=0.0)
    assert tools.spotify_control(ctx, "resume") == "OK (resume)."
    assert tools.spotify_control(ctx, "volume", 150) == "OK (volume)."
    assert tools.spotify_play(ctx, "queen") == "Lecture : Titre — Art"
    assert sp.device_calls == 1 and sp.played == ["pc", (100, "pc"), "pc"]
    sp.fail_once = True  # appareil en cache disparu → on le recherche une fois
    tools.spotify_control(ctx, "resume")
    assert sp.device_calls == 2
    with pytest.raises(tools.ToolError):
        tools.spotify_control(ctx, "danse")


def test_spotify_new_client_id_rebuilds_client(ctx):
    tools._SP.update(client=object(), cid="ancien", device="x")
    ctx.config["spotify_client_id"] = ""
    with pytest.raises(tools.ToolError, match="pas configuré"):
        tools._spotify(ctx)
    ctx.config["spotify_client_id"] = "nouveau"
    client = tools._spotify(ctx)
    assert tools._SP["cid"] == "nouveau" and tools._SP["device"] is None and client is tools._SP["client"]


def test_open_url():
    import webbrowser
    opened = []
    real = webbrowser.open
    webbrowser.open = opened.append
    try:
        tools.open_url(None, "exemple.fr")
        tools.open_url(None, "météo paris")
        tools.open_url(None, "http://a.b")
    finally:
        webbrowser.open = real
    assert opened == ["https://exemple.fr", "https://www.google.com/search?q=m%C3%A9t%C3%A9o%20paris", "http://a.b"]


# ───────── matériel ─────────

def test_format_snapshot_handles_missing_gpu_values():
    d = {"cpu": 12.0, "cpu_temp": None, "ram_percent": 50.0, "ram_used": 8 * hardware.GB,
         "ram_total": 16 * hardware.GB,
         "gpus": [{"name": "RTX", "util": None, "temp": None, "mem_used": None, "mem_total": 8192.0, "power": None},
                  {"name": "RTX2", "util": 99.0, "temp": 90.0, "mem_used": 4096.0, "mem_total": 8192.0, "power": 200.0}]}
    out = hardware.format_snapshot(d)
    assert "GPU RTX : ? % · ? °C" in out                     # avant : TypeError sur None
    assert "GPU RTX2 : 99 % · 90 °C · VRAM 4.0/8.0 Go · 200 W" in out and "⚠" in out


def test_gpu_status_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(hardware, "_query_gpus", lambda: calls.append(1) or [{"name": "G", "util": 1.0}])
    hardware._GPU_CACHE.update(time=0.0, data=[])
    a = hardware.gpu_status()
    a[0]["name"] = "modifié"
    assert hardware.gpu_status()[0]["name"] == "G" and len(calls) == 1
    hardware._GPU_CACHE["time"] = 0.0
    hardware.gpu_status()
    assert len(calls) == 2


def test_nvidia_smi_parsing(monkeypatch, tmp_path):
    class R:
        stdout = "NVIDIA RTX 4070, 65, 30, 2048, 12282, [N/A]\nbad line\n"
    monkeypatch.setattr(hardware, "_nvidia_smi", lambda: "nvidia-smi")
    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **k: R())
    g = hardware._query_gpus()
    assert g == [{"name": "NVIDIA RTX 4070", "temp": 65.0, "util": 30.0, "mem_used": 2048.0,
                  "mem_total": 12282.0, "power": None}]


# ───────── jeux ─────────

@pytest.fixture
def game(tmp_path, ctx):
    lib = tmp_path / "Jeux"
    root = lib / "SuperGame"
    (root / "data").mkdir(parents=True)
    (root / "bin").mkdir()
    (root / "data" / "items.json").write_text('{"x": 1}\n"Comrade\'s Hammer": "lieu: usine"\n', encoding="utf-8")
    (root / "data" / "loc.bin").write_bytes(b"\x00" * 5000 + "COMRADE'S HAMMER est ici".encode("utf-16-le")
                                           + b"\x00" * 5000)
    (root / "data" / "vide.dat").write_bytes(b"")
    (root / "data" / "tex.dds").write_bytes(b"comrade's hammer")    # extension ignorée
    (root / "bin" / "game.exe").write_bytes(b"MZ")
    ctx.config["game_folders"] = [str(lib)]
    games._LAST.update(name=None, root=None)
    return root


def test_search_game_files_text_and_binary(game, ctx, monkeypatch):
    monkeypatch.setattr(games, "_guide", lambda c, g, i: "(guide)")
    out = games.search_game_files(ctx, "comrade's hammer", game="supergame")
    assert "items.json (ligne 2)" in out
    assert "loc.bin (binaire)" in out and "tex.dds" not in out
    assert "3 fichiers lisibles lus" in out  # items.json, loc.bin, vide.dat


@pytest.mark.parametrize("cut", range(0, 40, 3))
def test_binary_search_across_chunk_boundaries(tmp_path, monkeypatch, cut):
    monkeypatch.setattr(games, "CHUNK", 64)
    needle = "Comrade's Hammer".encode("utf-16-le")
    data = b"\x01" * (64 - cut) + needle + b"\x02" * 300
    f = tmp_path / "x.bin"
    f.write_bytes(data)
    found = games._find_in_binary(str(f), games._patterns(["comrade's hammer"])[1])
    assert found is not None and "Comrade's Hammer" in found
    assert games._find_in_binary(str(f), games._patterns(["absent"])[1]) is None


def test_read_game_file(game, ctx):
    out = games.read_game_file(ctx, str(game / "data" / "items.json"), query="hammer")
    assert "2: \"Comrade's Hammer\"" in out
    assert "C\x00" not in games.read_game_file(ctx, str(game / "data" / "loc.bin"), query="comrade")
    assert games.read_game_file(ctx, str(game / "data" / "loc.bin"), query="absent") == "Mot non trouvé dans ce fichier."
    with pytest.raises(tools.ToolError):
        games.read_game_file(ctx, str(game / "nope.txt"))


def test_installed_and_detect_helpers(game, ctx, tmp_path):
    assert games.installed_games(ctx)[str(game)] == "SuperGame"
    assert "SuperGame" in games.list_games(ctx)
    root, name = games._match_library(str(game / "bin" / "game.exe").replace("/", "\\"), ctx)
    assert name == "SuperGame"
    with pytest.raises(tools.ToolError):
        games._resolve(ctx, "jeu inconnu")
    assert games._listdir(str(tmp_path / "absent")) == []
    assert games.profile("Cyberpunk 2077")["title"] == "Cyberpunk 2077" and games.profile("Tetris") is None


def test_flatten_and_variants():
    assert games._flatten({"a": {"b": 1, "c": [0, 2]}, "d": ""}) == {"a.b": 1, "a.c.1": 2}
    assert games._variants("Comrade  Hammer") == ["comrade hammer", "comrade_hammer", "comradehammer",
                                                  "comrade-hammer"]


# ───────── entretien ─────────

def test_clear_contents_never_follows_links(tmp_path):
    precious = tmp_path / "Documents"
    precious.mkdir()
    (precious / "important.docx").write_text("ne pas supprimer")
    cache = tmp_path / "cache"
    (cache / "sub").mkdir(parents=True)
    (cache / "a.tmp").write_bytes(b"x" * 100)
    (cache / "sub" / "b.tmp").write_bytes(b"y" * 50)
    os.symlink(precious, cache / "lien_vers_documents")
    freed = maintenance._clear_contents(str(cache))
    assert freed == 150 and os.listdir(cache) == []
    assert (precious / "important.docx").read_text() == "ne pas supprimer"
    assert maintenance._clear_contents(str(tmp_path / "absent")) == 0  # avant : FileNotFoundError


def test_analyze_and_clean(monkeypatch, tmp_path):
    cache = tmp_path / "tmpdir"
    cache.mkdir()
    (cache / "f").write_bytes(b"z" * 2048)
    monkeypatch.setattr(maintenance, "cache_targets", lambda: [("t", "Temp", str(cache), "contenu")])
    data = maintenance.analyze()
    assert data["caches"] == [{"key": "t", "label": "Temp", "size": 2048, "path": str(cache),
                               "kind": "contenu", "approx": False}]
    assert data["drives"][0]["total"] > 0
    freed, details = maintenance.clean(["t", "inconnu"])
    assert freed == 2048 and details == ["Temp : 0 Mo"]
    assert maintenance._fmt(3 * maintenance.GB) == "3.0 Go" and maintenance._fmt(5 * maintenance.MB) == "5 Mo"


def test_steam_appid_and_uninstall(tmp_path, monkeypatch):
    common = tmp_path / "steamapps" / "common" / "Portal"
    common.mkdir(parents=True)
    (tmp_path / "steamapps" / "appmanifest_400.acf").write_text('"appid" "400"\n"installdir" "Portal"')
    assert maintenance._steam_appid(str(common)) == "400"
    opened = []
    monkeypatch.setattr(maintenance, "_open", opened.append)
    assert "Steam" in maintenance.uninstall_game(str(common)) and opened == ["steam://uninstall/400"]
    other = tmp_path / "Autre" / "Jeu"
    other.mkdir(parents=True)
    (other / "unins000.exe").write_bytes(b"MZ")
    assert maintenance.uninstall_game(str(other)) == "Désinstalleur du jeu lancé."


# ───────── Mode Gaming ─────────

def test_close_list_ignores_empty_entries(ctx):
    ctx.config["gaming_close"] = ["", "  ", "OBS64.exe", "chrome", 42]
    lst = gaming._close_list(ctx)
    assert "" not in lst and "obs64" in lst and lst.count("chrome") == 1


def test_gaming_on_off_roundtrip(ctx, monkeypatch, tmp_path):
    import psutil

    class P:
        def __init__(self, name, exe):
            self.info = {"name": name, "exe": exe}
            self.terminated = False

        def terminate(self):
            self.terminated = True
    procs = [P("chrome.exe", str(tmp_path / "chrome.exe")), P("explorer.exe", "e"), P("game.exe", "g"),
             P("Discord.exe", "d")]
    (tmp_path / "chrome.exe").write_bytes(b"MZ")
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: procs)
    ctx.config["gaming_close"] = [""]  # avant : fermait TOUS les processus
    out = gaming.gaming_on(ctx)
    assert out.startswith("Mode Gaming activé : 1 app(s)") and [p.terminated for p in procs] == [True, False, False, False]
    opened = []
    monkeypatch.setattr(gaming, "_open", opened.append)
    assert gaming.gaming_off(ctx) == "Mode Gaming désactivé : 1 app(s) relancée(s)."
    assert opened == [str(tmp_path / "chrome.exe")] and gaming.gaming_off(ctx) == "Rien à relancer."


# ───────── Discord ─────────

def test_discord_oauth_flow_survives_favicon_and_can_retry(monkeypatch):
    def fake_browser(url):
        def visit():
            time.sleep(0.2)
            state = url.split("state=")[1].split("&")[0]
            base = f"http://127.0.0.1:{discord_auth.REDIRECT_PORT}"
            urllib.request.urlopen(f"{base}/callback?code=CODE123&state={state}").read()
            try:  # le navigateur demande ensuite l'icône : ça ne doit pas effacer le code
                urllib.request.urlopen(f"{base}/favicon.ico")
            except Exception:
                pass
        threading.Thread(target=visit, daemon=True).start()
        return True

    class Resp:
        status_code = 200

        def json(self):
            return {"access_token": "tok", "token_type": "Bearer", "expires_in": 3600}
    posted = []
    monkeypatch.setattr(discord_auth.webbrowser, "open", fake_browser)
    monkeypatch.setattr(discord_auth.requests, "post", lambda url, data, **k: posted.append(data) or Resp())
    monkeypatch.setattr(discord_auth, "account", lambda force=False: {"username": "max"})
    for _ in range(2):  # 2e tentative : avant, « port déjà utilisé » (socket jamais fermée)
        ok, msg = discord_auth.connect("cid", "secret", timeout=10)
        assert ok and msg == "Connecté en tant que max."
    assert posted[-1]["code"] == "CODE123" and discord_auth.is_connected()


def test_discord_oauth_rejects_bad_state(monkeypatch):
    def fake_browser(url):
        threading.Thread(target=lambda: (time.sleep(0.2), urllib.request.urlopen(
            f"http://127.0.0.1:{discord_auth.REDIRECT_PORT}/callback?code=X&state=pirate").read()),
            daemon=True).start()
    monkeypatch.setattr(discord_auth.webbrowser, "open", fake_browser)
    ok, msg = discord_auth.connect("cid", "secret", timeout=1.5)
    assert not ok


def test_discord_disconnect_clears_cached_account():
    discord_auth._CACHE["me"] = {"username": "max"}
    discord_auth._save_token({"access_token": "t"})
    discord_auth.disconnect()
    assert discord_auth.account() is None and not discord_auth.is_connected()


def test_discord_channels_cache_follows_token(ctx, monkeypatch):
    calls = []

    def fake_req(c, method, path, **kw):
        calls.append(path)
        if path == "/users/@me/guilds":
            return [{"id": "1", "name": "Potes"}]
        return [{"id": "10", "name": "général", "type": 0}, {"id": "11", "name": "vocal", "type": 2}]
    monkeypatch.setattr(discord_tools, "_req", fake_req)
    discord_tools._CACHE.update(channels=None, token=None)
    ctx.config["discord_bot_token"] = "A"
    assert discord_tools._find_channel(ctx, "potes/#gén")["id"] == "10"
    discord_tools._find_channel(ctx, "général")
    assert len(calls) == 2
    ctx.config["discord_bot_token"] = "B"
    discord_tools._find_channel(ctx, "général")
    assert len(calls) == 4
    with pytest.raises(tools.ToolError, match="introuvable"):
        discord_tools._find_channel(ctx, "vocal")


def test_discord_requires_token(ctx):
    ctx.config["discord_bot_token"] = ""
    assert tools.run("discord_channels", {}, ctx).startswith("Erreur : Pour lire ou écrire")


def test_config_fields_reference_known_keys():
    for key, *_ in config.FIELDS:
        assert key in config.DEFAULTS
