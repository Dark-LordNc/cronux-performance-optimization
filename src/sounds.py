"""Sons de notification (Windows). Pas de fichier externe : les sons sont générés avec winsound.

- message Discord  : deux petites notes montantes, discrètes
- appel Discord    : sonnerie répétée, plus insistante
- important        : une note douce
"""
import sys
import threading

IS_WIN = sys.platform == "win32"

try:
    import winsound  # Windows uniquement
except Exception:
    winsound = None

# Mots qui indiquent un appel plutôt qu'un simple message
CALL_WORDS = ("appel", "calling", "is calling", "ringing", "appel entrant", "incoming call",
              "started a call", "a démarré un appel", "t'appelle", "vous appelle")


def _beep(sequence):
    if not winsound:
        return
    try:
        for freq, ms in sequence:
            if freq == 0:
                import time
                time.sleep(ms / 1000)
            else:
                winsound.Beep(freq, ms)
    except Exception:
        pass


def _play(sequence):
    threading.Thread(target=_beep, args=(sequence,), daemon=True).start()


def message():
    """Deux notes brèves, montantes."""
    _play([(784, 90), (988, 110)])


def call():
    """Sonnerie plus insistante (motif répété)."""
    ring = [(988, 180), (784, 180), (0, 120)]
    _play(ring * 3)


def important():
    """Une note douce pour une notif importante non-Discord."""
    _play([(660, 120)])


def is_call(notif):
    text = f"{notif.get('title', '')} {notif.get('body', '')}".lower()
    return any(w in text for w in CALL_WORDS)


def play_for(notif):
    """Choisit le bon son selon la notification."""
    app = (notif.get("app") or "").lower()
    if "discord" in app:
        call() if is_call(notif) else message()
    elif notif.get("important"):
        important()


def test(kind="message"):
    {"message": message, "call": call, "important": important}.get(kind, message)()
