"""Mesure des chemins « chauds » de Cronux. Usage : python tests/bench.py [dossier_src]
Permet de comparer deux versions (ex. l'ancienne et la nouvelle) sur la même machine."""
import os
import sys
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="cronux_bench_")
SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC)

import config  # noqa: E402
import games  # noqa: E402
import memory  # noqa: E402
import notifications  # noqa: E402
import tools  # noqa: E402


def bench(label, fn, n):
    fn()
    t = time.perf_counter()
    for _ in range(n):
        fn()
    dt = (time.perf_counter() - t) / n
    print(f"{label:<52} {dt * 1e6:>10.1f} µs/appel")


for i in range(150):
    memory.remember(None, f"Souvenir numéro {i} : un fait utile sur l'utilisateur")
for i in range(20):
    memory.remember(None, f"[notif] Les notifications de App{i} « Titre {i} » ne sont pas importantes")
notifications.add([{"id": i, "app": "Discord", "title": f"t{i}", "body": "x" * 200, "time": "2026-10-08 10:00",
                    "important": i % 3 == 0, "reason": "", "seen": False} for i in range(1, 301)])
batch = [{"id": i, "app": "Mail", "title": f"m{i}", "body": ""} for i in range(15)]

bench("config.load()  (surveillance : toutes les 4 s)", config.load, 300)
bench("memory.prompt_block()  (à chaque étape de l'IA)", memory.prompt_block, 300)
if hasattr(notifications, "learned_rules"):
    bench("règles apprises pour 15 notifications", lambda: [notifications.learned_rule(i, r) for r in
                                                           [notifications.learned_rules()] for i in batch], 100)
else:
    bench("règles apprises pour 15 notifications", lambda: [notifications.learned_rule(i) for i in batch], 100)
bench("notifications.unseen_important()  (badge 🔔)", notifications.unseen_important, 300)
bench("notifications.recent(60)  (panneau)", lambda: notifications.recent(count=60), 300)

game = tempfile.mkdtemp(prefix="cronux_game_")
for k in range(6):
    with open(os.path.join(game, f"data{k}.bin"), "wb") as f:
        f.write(os.urandom(12 * 1024 * 1024))
ctx = tools.Context(config.load(), lambda *a: True)
ctx.config["game_folders"] = [os.path.dirname(game)]
games._guide = lambda c, g, i: ""
name = os.path.basename(game)
bench("search_game_files sur 72 Mo de binaires", lambda: games.search_game_files(ctx, "comrade hammer", name), 3)
try:
    import resource
    print(f"{'pic de mémoire du processus':<52} {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:>10.0f} Mo")
except ImportError:
    pass
