"""Interface (nécessite un écran : lancer sous Xvfb, ex. `xvfb-run -a python -m pytest`)."""
import os
import threading
import time

import pytest

if not os.environ.get("DISPLAY"):
    pytest.skip("pas d'écran (lancer sous xvfb-run)", allow_module_level=True)
pytest.importorskip("tkinter")

import main  # noqa: E402
import maintenance  # noqa: E402
import tools  # noqa: E402


def pump(app, seconds=0.3, until=None):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until else True


@pytest.fixture
def app():
    a = main.App()
    errors = []
    a.report_callback_exception = lambda *exc: errors.append(exc)
    pump(a, 0.3)
    yield a
    try:
        a.destroy()
    except Exception:
        pass
    assert not errors, errors


def test_all_panels_open_and_close(app):
    for opener in ("open_settings", "open_memory", "open_notifs", "open_spotify", "open_discord",
                   "open_maintenance", "open_gaming", "toggle_overlay"):
        getattr(app, opener)()
        pump(app, 0.3)
        getattr(app, opener)()  # 2e clic : réutilise / ferme la fenêtre sans erreur
        pump(app, 0.2)
    for w in (app.settings_win, app.memory_win, app.panel, app.spotify_win, app.discord_win,
              app.maint_win, app.gaming_win):
        w.destroy()
    pump(app, 0.3)  # les réponses d'arrière-plan qui arrivent après fermeture sont ignorées


def test_call_ui_from_thread_runs_on_ui_thread(app):
    seen = []
    t = threading.Thread(target=lambda: app.call_ui(lambda: seen.append(threading.get_ident())))
    t.start()
    t.join()
    assert pump(app, 2, until=lambda: seen)
    assert seen == [threading.get_ident()]


def test_run_bg_result_and_error(app):
    got = []
    app.run_bg(lambda: 41 + 1, got.append)
    app.run_bg(lambda: 1 / 0, None, lambda e: got.append(type(e).__name__))
    assert pump(app, 2, until=lambda: len(got) == 2)
    assert sorted(map(str, got)) == ["42", "ZeroDivisionError"]


def test_maintenance_error_is_displayed(app, monkeypatch):
    def boom():
        raise PermissionError("accès refusé")
    monkeypatch.setattr(maintenance, "analyze", boom)
    app.open_maintenance()
    win = app.maint_win
    assert pump(app, 3, until=lambda: "Erreur" in win.msg.cget("text"))   # avant : NameError
    assert "accès refusé" in win.msg.cget("text")


def test_maintenance_render_and_clean(app, monkeypatch):
    monkeypatch.setattr(maintenance, "analyze", lambda: {
        "drives": [{"drive": "C:\\", "total": 100 * maintenance.GB, "free": 40 * maintenance.GB, "used": 0}],
        "caches": [{"key": "t", "label": "Temp", "size": 5 * maintenance.MB}]})
    monkeypatch.setattr(maintenance, "unused_games", lambda ctx: [
        {"name": "Vieux jeu", "root": "x", "size": maintenance.GB, "inactive_days": 90, "last": 0}])
    monkeypatch.setattr(maintenance, "clean", lambda keys: (5 * maintenance.MB, []))
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *a, **k: True)
    app.open_maintenance()
    win = app.maint_win
    assert pump(app, 3, until=lambda: "40.0 Go libres" in win.disk.cget("text"))
    assert list(win.cache_vars) == ["t"]
    win._clean()
    assert pump(app, 3, until=lambda: "libérés" in win.msg.cget("text"))
    pump(app, 0.5)  # la nouvelle analyse est terminée : le message est toujours là
    assert win.msg.cget("text") == "✓ 5 Mo libérés" and win.clean_btn.cget("state") == "normal"


def test_chat_bubbles_are_capped(app, monkeypatch):
    monkeypatch.setattr(main, "MAX_BUBBLES", 20)
    for i in range(45):
        app.add_bubble(f"message **{i}**", "user" if i % 2 else "bot")
    pump(app, 0.2)
    assert len(app.labels) == 20 and len(app.chat.winfo_children()) == 20
    assert app.labels[-1].cget("text") == "message 44"


def test_resize_rewraps_once_and_ignores_children(app):
    for i in range(10):
        app.add_bubble(f"bulle {i}", "bot")
    pump(app, 0.3)
    calls = []
    real = app._apply_wrap
    app._apply_wrap = lambda: calls.append(1) or real()
    for w in app.labels:  # événements <Configure> des enfants : ignorés
        w.event_generate("<Configure>")
    for size in ("500x700", "520x700", "560x700"):
        app.geometry(size)
        app.update()
    pump(app, 0.5)
    assert len(calls) == 1
    assert app.labels[0].cget("wraplength") == app._wrap()


def test_toasts_are_capped(app):
    for i in range(8):
        app._show_toast({"app": "Discord", "title": f"Paul {i}", "body": "salut", "important": False})
    pump(app, 0.3)
    assert len(app.toasts) == main.MAX_TOASTS
    assert [t.winfo_exists() for t in app.toasts] == [1] * main.MAX_TOASTS
    app._on_close()


def test_new_notifications_flow(app, monkeypatch):
    played = []
    monkeypatch.setattr(main.sounds, "play_for", played.append)
    notif = {"id": 1, "app": "Discord", "title": "Paul", "body": "", "important": True,
             "time": "2026-10-08 10:00"}
    app._on_new_notifs([notif])
    pump(app, 0.2)
    assert played == [notif] and len(app.toasts) == 1
    assert "Paul" in app.labels[-1].cget("text")


def test_confirm_from_ui_thread_and_worker(app, monkeypatch):
    answers = []
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *a, **k: True)
    assert app.confirm("t", "m") is True  # depuis l'interface : pas de blocage
    t = threading.Thread(target=lambda: answers.append(app.confirm("t", "m")))
    t.start()
    assert pump(app, 3, until=lambda: answers)
    t.join(1)
    assert answers == [True]


def test_spotify_volume_is_debounced(app, monkeypatch):
    calls = []
    monkeypatch.setattr(tools, "spotify_control", lambda ctx, action, *a: calls.append((action, a)) or "OK")
    monkeypatch.setattr(tools, "spotify_now_playing", lambda ctx: "Rien en lecture.")
    app.open_spotify()
    win = app.spotify_win
    for v in range(0, 100, 5):
        win._volume(v)
        app.update()
    assert pump(app, 2, until=lambda: calls)
    pump(app, 0.4)
    assert calls == [("volume", (95,))]   # avant : 20 requêtes Spotify


def test_send_message_end_to_end(app, monkeypatch):
    monkeypatch.setattr(app.agent, "ask", lambda text, on_status: (on_status("Réflexion…"), f"écho : {text}")[1])
    app.entry.insert(0, "bonjour")
    app.send()
    assert app.busy
    assert pump(app, 3, until=lambda: not app.busy)
    assert app.labels[-1].cget("text") == "écho : bonjour"
    assert app.send_btn.cget("state") == "normal"
