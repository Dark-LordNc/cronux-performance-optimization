"""Test de fumée de l'interface (à lancer sous Xvfb) : ouvre la fenêtre et tous les panneaux."""
import os
import sys
import tempfile
import time

os.environ.setdefault("APPDATA", tempfile.mkdtemp(prefix="cronux_gui_"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import main  # noqa: E402


def pump(app, seconds=0.5):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


app = main.App()
pump(app, 1)
errors = []
app.report_callback_exception = lambda *a: errors.append(a)
for opener in ("open_settings", "open_memory", "open_notifs", "open_spotify", "open_discord",
               "open_maintenance", "open_gaming", "toggle_overlay"):
    getattr(app, opener)()
    pump(app, 0.6)
    print("ok", opener)
for i in range(30):
    app.add_bubble(f"message **{i}**", "user" if i % 2 else "bot")
app._on_new_notifs([{"id": 1, "app": "Discord", "title": "Paul", "body": "salut", "important": True,
                     "time": "2026-10-08 10:00"}])
pump(app, 1)
app.geometry("600x700")
pump(app, 0.5)
app.toggle_overlay()
app.new_chat()
pump(app, 0.5)
app.destroy()
if errors:
    print("ERREURS TK:", errors)
    sys.exit(1)
print("GUI_SMOKE_OK")
