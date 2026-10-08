"""Config, mémoire et historique des notifications (fichiers JSON + caches)."""
import json
import os
import sqlite3
import time

import pytest

import config
import memory
import notifications


def _bump_mtime(path):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


# ───────── config ─────────

def test_config_defaults_created():
    cfg = config.load()
    assert cfg["model"] == config.DEFAULTS["model"]
    with open(config.CONFIG_PATH, encoding="utf-8") as f:
        assert set(json.load(f)) >= set(config.DEFAULTS)


def test_config_load_does_not_rewrite_file_each_time():
    config.load()
    before = os.stat(config.CONFIG_PATH).st_mtime_ns
    time.sleep(0.02)
    for _ in range(50):
        config.load()
    assert os.stat(config.CONFIG_PATH).st_mtime_ns == before


def test_config_returns_independent_copies():
    cfg = config.load()
    cfg["search_folders"].append("X")
    cfg["model"] = "modifié"
    again = config.load()
    assert again["search_folders"] == [] and again["model"] == config.DEFAULTS["model"]


def test_config_update_persists_and_external_edit_is_seen():
    config.update({"user_name": "Max"})
    assert config.load()["user_name"] == "Max"
    data = json.load(open(config.CONFIG_PATH, encoding="utf-8"))
    data["user_name"] = "Léa"
    with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    _bump_mtime(config.CONFIG_PATH)
    assert config.load()["user_name"] == "Léa"


def test_config_corrupt_file_is_backed_up_not_lost():
    os.makedirs(config.APP_DIR, exist_ok=True)
    with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write('{"user_name": "Max", ')  # JSON tronqué
    cfg = config.load()
    assert cfg["user_name"] == ""
    with open(config.CONFIG_PATH + ".bak", encoding="utf-8") as f:
        assert '"Max"' in f.read()


def test_config_missing_keys_are_added():
    with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"user_name": "Max"}, f)
    cfg = config.load()
    assert cfg["user_name"] == "Max" and "gaming_close" in cfg
    assert "gaming_close" in json.load(open(config.CONFIG_PATH, encoding="utf-8"))


# ───────── mémoire ─────────

def test_remember_forget_and_dedupe():
    assert memory.remember(None, "Sa sœur s'appelle Léa").startswith("Retenu")
    assert memory.remember(None, "sa sœur s'appelle léa") == "Déjà en mémoire."
    facts = memory.all_facts()
    assert len(facts) == 1 and facts[0]["id"] == 1
    memory.forget(None, 1)
    assert memory.all_facts() == []
    with pytest.raises(memory.ToolError):
        memory.forget(None, 99)


def test_memory_readers_get_copies():
    memory.remember(None, "fait A")
    memory.all_facts()[0]["text"] = "corrompu"
    memory.last_conversation().append({"role": "user", "content": "x"})
    assert memory.all_facts()[0]["text"] == "fait A"
    assert memory.last_conversation() == []


def test_memory_cache_sees_external_changes():
    memory.remember(None, "fait A")
    assert "fait A" in memory.prompt_block()
    data = json.load(open(memory.PATH, encoding="utf-8"))
    data["facts"][0]["text"] = "fait B"
    with open(memory.PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    _bump_mtime(memory.PATH)
    assert "fait B" in memory.prompt_block()


def test_memory_cache_avoids_rereading(monkeypatch):
    memory.remember(None, "fait A")
    memory.prompt_block()
    calls = []
    real = json.load
    monkeypatch.setattr(memory.json, "load", lambda f: calls.append(1) or real(f))
    for _ in range(100):
        memory.prompt_block()
        memory.all_facts()
    assert calls == []


def test_habits_and_conversation():
    for _ in range(3):
        memory.record_usage("launch_app", {"name": "Spotify"}, "Spotify lancé.")
    memory.record_usage("launch_app", {"name": "Word"}, "Erreur : introuvable")
    summary = memory.habits_summary()
    assert len(summary) == 1 and "spotify" in summary[0] and "3×" in summary[0]
    assert "SES HABITUDES" in memory.prompt_block()
    history = [{"role": "user", "content": "a" * 1000}, {"role": "tool", "content": "x"},
               {"role": "assistant", "content": "ok"}]
    memory.save_conversation(history)
    conv = memory.last_conversation()
    assert [m["role"] for m in conv] == ["user", "assistant"] and len(conv[0]["content"]) == 600


def test_memory_corrupt_file_is_tolerated():
    with open(memory.PATH, "w", encoding="utf-8") as f:
        f.write("[1, 2")
    assert memory.all_facts() == [] and memory.prompt_block() == ""
    memory.remember(None, "nouveau")
    assert memory.all_facts()[0]["text"] == "nouveau"


# ───────── notifications ─────────

def _payload(*texts):
    inner = "".join(f"<text>{t}</text>" for t in texts)
    return f"<toast><visual><binding template='ToastGeneric'>{inner}</binding></visual></toast>"


def make_wpn_db(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE NotificationHandler (RecordId INTEGER PRIMARY KEY, PrimaryId TEXT)")
    con.execute("CREATE TABLE Notification (Id INTEGER PRIMARY KEY, HandlerId INTEGER, Type TEXT, "
                "Payload BLOB, ArrivalTime INTEGER)")
    handlers = {}
    for nid, primary, payload, kind in rows:
        if primary not in handlers:
            handlers[primary] = len(handlers) + 1
            con.execute("INSERT INTO NotificationHandler VALUES (?, ?)", (handlers[primary], primary))
        con.execute("INSERT INTO Notification VALUES (?, ?, ?, ?, ?)",
                    (nid, handlers[primary], kind, payload.encode("utf-8"), 133_000_000_000_000_000))
    con.commit()
    con.close()


def test_read_db_parses_and_filters(tmp_path):
    db = str(tmp_path / "wpndatabase.db")
    make_wpn_db(db, [
        (1, "com.squirrel.Discord.Discord", _payload("Paul", "salut ça va ?"), "toast"),
        (2, "Cronux", _payload("interne"), "toast"),                       # ignorée (Cronux lui-même)
        (3, "Microsoft.Outlook_8wekyb3d8bbwe!App", _payload("Facture", "Votre paiement"), "toast"),
        (4, "Some.App", _payload("badge"), "tile"),                          # pas un toast
        (5, "C:\\Games\\Steam\\steam.exe", "<toast>pas du xml", "toast"),    # XML cassé → ignorée
    ])
    max_id, items = notifications.read_db(0, 100, db_path=db)
    assert max_id == 5
    assert [(i["id"], i["app"], i["title"], i["body"]) for i in items] == [
        (1, "Discord", "Paul", "salut ça va ?"),
        (3, "Outlook", "Facture", "Votre paiement"),
    ]
    assert notifications.read_db(5, 100, db_path=db) == (5, [])


def test_store_add_recent_seen_and_badge():
    items = [{"id": i, "app": "Discord" if i % 2 else "Mail", "title": f"t{i}", "body": "",
              "time": "2026-10-08 10:00", "important": i in (2, 3), "reason": "", "seen": False}
             for i in range(1, 6)]
    notifications.add(items)
    assert notifications.unseen_important() == 2
    assert [i["id"] for i in notifications.recent(count=3)] == [5, 4, 3]
    assert [i["id"] for i in notifications.recent(only_important=True)] == [3, 2]
    assert [i["id"] for i in notifications.recent(app="discord")] == [5, 3, 1]
    notifications.recent()[0]["title"] = "corrompu"
    assert notifications.recent()[0]["title"] == "t5"
    notifications.set_importance(5, True)
    assert notifications.recent(only_important=True)[0]["reason"] == "choisi par toi"
    notifications.mark_all_seen()
    assert notifications.unseen_important() == 0
    before = os.stat(notifications.STORE).st_mtime_ns
    notifications.mark_all_seen()  # rien à changer → pas d'écriture
    assert os.stat(notifications.STORE).st_mtime_ns == before
    notifications.add(items)  # doublons ignorés
    assert len(notifications.recent(count=100)) == 5


def test_learned_rules_latest_wins_and_heuristic():
    memory.remember(None, "[notif] Les notifications de Discord « Serveur X » ne sont pas importantes")
    memory.remember(None, "[notif] Les notifications de Discord « Serveur X » sont importantes")
    rules = notifications.learned_rules()
    item = {"app": "discord", "title": "Serveur X", "body": ""}
    assert notifications.learned_rule(item, rules) is True
    assert notifications.learned_rule({"app": "Mail", "title": "Y", "body": ""}) is None
    assert notifications.heuristic({"title": "Code de vérification", "body": ""})["important"] is True
    assert notifications.heuristic({"title": "Promo -50%", "body": "soldes"})["important"] is False


def test_db_changed_tolerates_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(notifications, "DB", str(tmp_path / "absent.db"))
    notifications._MTIME["v"] = None
    assert notifications.db_changed() is True
    assert notifications.db_changed() is False
    (tmp_path / "absent.db").write_text("x")
    assert notifications.db_changed() is True
