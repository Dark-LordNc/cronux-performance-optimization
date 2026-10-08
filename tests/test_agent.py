"""Agent : dialogue avec un faux serveur Ollama, enchaînement d'outils, tri des notifications."""
import http.server
import json
import threading
import time

import pytest

import agent
import config
import memory
import tools


class FakeOllama:
    """Petit serveur HTTP qui imite /api/chat et /api/tags d'Ollama."""

    def __init__(self):
        self.replies = []       # réponses /api/chat, dans l'ordre
        self.requests = []      # corps reçus sur /api/chat
        self.models = ["qwen2.5:14b", "llama3:latest"]
        self.delay = 0
        self.connections = set()
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _send(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                fake.connections.add(self.client_address)
                self._send(200, {"models": [{"name": m} for m in fake.models]})

            def do_POST(self):
                fake.connections.add(self.client_address)
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(data)
                time.sleep(fake.delay)
                if not fake.replies:
                    return self._send(404, {"error": "model not found"})
                self._send(200, {"message": fake.replies.pop(0)})

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def ollama():
    fake = FakeOllama()
    config.update({"ollama_url": fake.url, "model": "qwen2.5:14b"})
    agent._TLS.__dict__.clear()  # pas de session HTTP gardée d'un test à l'autre
    yield fake
    fake.close()


def test_same_model():
    assert agent._same_model("qwen2.5:latest", "qwen2.5")
    assert agent._same_model("qwen2.5:14b", "qwen2.5:14b")
    assert not agent._same_model("qwen2.5:14b", "qwen2.5")       # Ollama chercherait qwen2.5:latest
    assert not agent._same_model("qwen2.5:7b", "qwen2.5:14b")


def test_check_ollama_and_model_installed(ollama):
    assert agent.check_ollama() is None
    assert agent.model_installed(model="llama3") is True
    assert agent.model_installed(model="qwen2.5") is False         # avant : considéré comme installé
    config.update({"model": "qwen2.5"})
    assert "n'est pas installé" in agent.check_ollama()


def test_ollama_unreachable():
    config.update({"ollama_url": "http://127.0.0.1:9"})
    assert agent.model_installed() is None
    assert "Ollama ne semble pas lancé" in agent.check_ollama()
    a = agent.Agent(confirm=lambda *a: True)
    with pytest.raises(RuntimeError, match="Ollama ne répond pas"):
        a.ask("salut")


def test_ask_runs_tools_until_answer(ollama, monkeypatch):
    calls = []
    monkeypatch.setitem(tools.REGISTRY["get_datetime"], "fn", lambda ctx: calls.append(1) or "lundi 10h")
    ollama.replies = [
        {"content": "", "tool_calls": [{"function": {"name": "get_datetime", "arguments": {"bidon": 1}}}]},
        {"content": "", "tool_calls": [{"function": {"name": "remember",
                                                     "arguments": '{"fact": "Aime le jazz"}'}}]},
        {"content": "C'est lundi, **10h**."},
    ]
    prompt_calls = []
    real_block = memory.prompt_block
    monkeypatch.setattr(memory, "prompt_block", lambda: prompt_calls.append(1) or real_block())
    statuses = []
    a = agent.Agent(confirm=lambda *a: True)
    assert a.ask("quelle heure ?", on_status=statuses.append) == "C'est lundi, **10h**."
    assert len(calls) == 1 and memory.all_facts()[0]["text"] == "Aime le jazz"
    assert "⚙ Je regarde l'heure…" in statuses
    # Le prompt système est construit une seule fois et identique à chaque étape (cache d'Ollama).
    assert len(prompt_calls) == 1
    systems = [r["messages"][0]["content"] for r in ollama.requests]
    assert len(systems) == 3 and len(set(systems)) == 1
    assert ollama.requests[0]["keep_alive"] == "60m" and ollama.requests[0]["options"]["num_ctx"] == 16384
    roles = [m["role"] for m in ollama.requests[-1]["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool"]
    # Une seule connexion TCP réutilisée (keep-alive) pour les 3 appels.
    assert len({port for _, port in ollama.connections}) == 1
    assert memory.last_conversation()[-1]["content"] == "C'est lundi, **10h**."


def test_ask_hints_after_failure_and_gives_up(ollama):
    failing = {"content": "", "tool_calls": [{"function": {"name": "outil_inexistant", "arguments": {}}}]}
    ollama.replies = [dict(failing) for _ in range(agent.MAX_STEPS)]
    a = agent.Agent(confirm=lambda *a: True)
    reply = a.ask("fais un truc")
    assert "pas réussi" in reply
    notes = [m for m in a.history if m["role"] == "user" and "note interne" in m["content"]]
    assert len(notes) == agent.MAX_STEPS


def test_model_missing_message(ollama):
    ollama.replies = []
    with pytest.raises(RuntimeError, match="ollama pull qwen2.5:14b"):
        agent.Agent(confirm=lambda *a: True).ask("salut")


def test_timeout_gives_friendly_message(ollama):
    ollama.delay = 1.5
    ollama.replies = [{"content": "trop tard"}]
    with pytest.raises(RuntimeError, match="trop de temps"):
        agent._post_chat(config.load(), {"model": "x", "messages": []}, timeout=0.3)


def test_history_is_bounded_and_trimmed_to_user_turn():
    a = agent.Agent(confirm=lambda *a: True)
    a.history = [{"role": "tool", "content": "x"}] * 3 + [{"role": "user", "content": "u"}] * 300
    assert a._trimmed()[0]["role"] == "user"
    a.history = [{"role": "assistant", "content": "a"}, {"role": "tool", "content": "t"},
                 {"role": "user", "content": "u"}]
    assert [m["role"] for m in a._trimmed()] == ["user"]


def test_salvage_args():
    assert agent._salvage_args('{"a": 1}') == {"a": 1}
    assert agent._salvage_args('voici {"a": 2} voilà') == {"a": 2}
    assert agent._salvage_args("pas du json") == {}
    assert agent._salvage_args(None) == {}
    assert agent._salvage_args({"b": 3}) == {"b": 3}


def _notif(i, title, app="Mail"):
    return {"id": i, "app": app, "title": title, "body": "", "important": False, "reason": ""}


def test_classify_uses_rules_ai_and_fallback(ollama):
    memory.remember(None, "[notif] Les notifications de Discord « Serveur » ne sont pas importantes")
    ollama.replies = [{"content": json.dumps({"resultats": [{"id": 2, "important": True, "raison": "proche"}]})}]
    items = [_notif(1, "Serveur", "Discord"), _notif(2, "Maman"), _notif(3, "Code de vérification")]
    agent.classify_notifications(items)
    assert (items[0]["important"], items[0]["reason"]) == (False, "règle apprise")
    assert (items[1]["important"], items[1]["reason"]) == (True, "proche")
    assert (items[2]["important"], items[2]["reason"]) == (True, "mot-clé")   # absent de la réponse → mots-clés
    assert len(ollama.requests) == 1 and "Serveur" not in ollama.requests[0]["messages"][1]["content"]


def test_classify_respects_time_budget(ollama):
    ollama.delay = 3
    ollama.replies = [{"content": "{}"}]
    items = [_notif(1, "Promo"), _notif(2, "Urgent : rappel")]
    start = time.monotonic()
    agent.classify_notifications(items, time_budget=1)
    assert time.monotonic() - start < 2.5
    assert [i["important"] for i in items] == [False, True]
