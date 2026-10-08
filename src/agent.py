"""Le « cerveau » de Cronux : dialogue avec Ollama, exécution des outils, tri des notifications."""
import json
import os
import threading
import time

import requests

import config
import memory
import tools
# Ces imports enregistrent leurs outils
import discord_tools  # noqa: F401
import games  # noqa: F401
import maintenance  # noqa: F401
import hardware  # noqa: F401
import gaming  # noqa: F401
import notifications

MAX_STEPS = 12
MAX_HISTORY = 44


_TLS = threading.local()


def _session():
    """Une session HTTP par thread : la connexion à Ollama est réutilisée (keep-alive) au lieu
    d'ouvrir un nouveau socket à chaque appel."""
    s = getattr(_TLS, "session", None)
    if s is None:
        s = _TLS.session = requests.Session()
    return s


def _base_url(cfg):
    return (cfg.get("ollama_url") or config.DEFAULTS["ollama_url"]).rstrip("/")


def _post_chat(cfg, payload, timeout=300):
    opts = payload.setdefault("options", {})
    opts.setdefault("num_ctx", int(cfg.get("context_tokens", 16384)))
    opts.setdefault("num_predict", 1024)   # évite les réponses tronquées sans partir en roue libre
    opts.setdefault("top_p", 0.9)
    # Garde le modèle chargé : sinon le recharger prend 10-20 s et retarde les notifications
    payload.setdefault("keep_alive", f"{int(cfg.get('keep_model_loaded_minutes', 60))}m")
    url = _base_url(cfg) + "/api/chat"
    try:
        r = _session().post(url, json=payload, timeout=timeout)
    except requests.ConnectionError:
        raise RuntimeError("Ollama ne répond pas. Vérifie qu'il est lancé (icône du lama dans la barre des tâches).")
    except requests.Timeout:
        raise RuntimeError("Ollama met trop de temps à répondre. Essaie un modèle plus léger "
                           "(⚙ → Modèle Ollama) ou baisse la mémoire de travail.")
    if r.status_code == 404:
        raise RuntimeError(f"Le modèle « {cfg['model']} » n'est pas installé. "
                           f"Ouvre un terminal et tape : ollama pull {cfg['model']}")
    r.raise_for_status()
    return r.json()["message"]


def _installed_models(cfg):
    """Liste des modèles installés dans Ollama, ou None s'il est injoignable."""
    try:
        r = _session().get(_base_url(cfg) + "/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return None


def _same_model(installed, wanted):
    """Ollama ajoute « :latest » quand on ne précise pas de tag : « qwen2.5 » = « qwen2.5:latest »."""
    def full(name):
        return name if ":" in name else name + ":latest"
    return full(installed.strip()) == full(wanted.strip())


def _salvage_args(raw):
    """Récupère les arguments d'un outil même si le modèle renvoie un JSON légèrement cassé."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass
    return {}


class Agent:
    def __init__(self, confirm):
        self.confirm = confirm
        # Reprend la fin de la conversation précédente (même après redémarrage du PC)
        self.history = list(memory.last_conversation())
        self._schemas = None

    def reset(self):
        self.history = []
        memory.save_conversation([])

    def _system(self, cfg):
        name = cfg.get("user_name") or "l'utilisateur"
        prompt = (
            f"Tu es Cronux, l'assistant personnel de {name} sur son PC Windows. Tu es malin, posé et efficace.\n"
            f"Date et heure : {tools.get_datetime(None)}. Dossier personnel : {os.path.expanduser('~')}.\n\n"

            "MÉTHODE (suis-la à chaque demande) :\n"
            "1. Comprends la VRAIE intention, même si la demande est vague, familière ou mal orthographiée. "
            "Appuie-toi sur ce que tu sais de l'utilisateur et sur ses habitudes ci-dessous.\n"
            "2. Si une action est demandée, UTILISE un outil — ne te contente jamais de décrire la marche à suivre.\n"
            "3. Enchaîne les outils jusqu'au bout : d'abord celui qui trouve (search_files, list_emails, detect_game…), "
            "puis celui qui agit (open_path, read_email…). Ne réponds qu'une fois l'objectif atteint.\n"
            "4. Si un outil renvoie une erreur ou rien, NE RÉESSAIE PAS à l'identique : change d'approche "
            "(autres mots-clés, nom anglais, autre dossier, autre outil) avant d'abandonner.\n"
            "5. Réponds en français, en tutoyant, court et clair (2-4 phrases). Dis ce que tu as fait, pas comment.\n"
            "6. Ne pose une question que si c'est vraiment ambigu, et une seule. N'invente jamais un résultat.\n\n"

            "EXEMPLES de raisonnement :\n"
            "- « ouvre ma facture edf » → search_files(query='facture edf') → open_path(chemin trouvé le plus récent).\n"
            "- « mets ma musique » → spotify_play sans query reprend, ou lance ce qu'il écoute le plus (habitudes).\n"
            "- « répond à paul que c'est ok » → search_emails(query='Paul') → reply_email(id, 'C'est ok pour moi.').\n"
            "- « où je trouve le marteau » (en jeu) → detect_game → search_game_files(item='Comrade's Hammer').\n"
            "- « c'est quoi ce truc ouvert qui rame » → list_running_apps.\n\n"

            "APPRENTISSAGE (important) :\n"
            "- Dès que l'utilisateur révèle une info durable (proche, mail, pseudo, projet, jeu, préférence, horaire), "
            "appelle remember tout de suite, sans le lui demander. S'il te corrige : forget puis remember.\n"
            "- S'il dit qu'un type de notif est (ou non) important, remember une règle commençant par « [notif] ».\n\n"

            "OUTILS (rappels) :\n"
            "- Fichiers : search_files → open_path. Apps/jeux ouverts : list_running_apps. Lancer une app : launch_app.\n"
            "- Mails Outlook : list_emails / search_emails → read_email / reply_email / send_email.\n"
            "- Agenda : list_events / create_event. Spotify : spotify_play / spotify_control / spotify_now_playing.\n"
            "- Notifications triées : list_notifications (app='Discord' pour les messages Discord reçus).\n"
            "- Discord serveurs/MP : discord_channels, discord_read, discord_send, discord_dm.\n"
            "- Jeux : detect_game (ou list_games), puis search_game_files (nom ANGLAIS de l'objet, traduis la réponse). "
            "game_save_info donne la progression. web_search / web_read pour compléter. Jamais la mémoire du jeu.\n"
            "- Pour connecter Discord : dis d'ouvrir ⚙ → « Ouvrir la connexion Discord » (bouton « Se connecter avec Discord »). "
            "La connexion officielle donne l'identité et la liste des serveurs ; lire/écrire les messages nécessite le bot "
            "(un compte perso automatisé est interdit). Pour Spotify, la mémoire ou un réglage : ouvrir ⚙ ou 🧠.\n"
            "- Matériel : hardware_status (CPU/RAM/GPU, alerte si ça chauffe). Mode Gaming : gaming_mode state=on/off "
            "(ferme/relance les apps gourmandes). Capture : screenshot, screenshot_to_discord.\n"
            "- Entretien PC : disk_report (espace + ce qui est nettoyable), clean_cache (libère de l'espace, avec confirmation), "
            "unused_games (jeux délaissés + taille), uninstall_game (lance la désinstallation officielle). "
            "Propose le nettoyage ou la désinstallation, mais ne supprime jamais sans confirmation.\n"
            "- Cheat Engine / modifier la mémoire d'un jeu : REFUSE poliment (triche, risque de bannissement). "
            "Propose à la place les options officielles du jeu, ses fichiers de config, ou les mods autorisés.\n"
            "- Dates au format AAAA-MM-JJ HH:MM ; calcule « demain », « lundi »… depuis maintenant."
        )
        mem = memory.prompt_block()
        return prompt + ("\n\nCE QUE TU SAIS DÉJÀ :\n" + mem if mem else "")

    def _trimmed(self):
        h = self.history[-MAX_HISTORY:]
        start = 0
        while start < len(h) and h[start].get("role") != "user":  # ne pas commencer au milieu d'un appel d'outil
            start += 1
        return h[start:]

    def _tool_schemas(self):
        # Les outils sont tous enregistrés à l'import : inutile de reconstruire la liste à chaque étape.
        if self._schemas is None or len(self._schemas) != len(tools.REGISTRY):
            self._schemas = tools.schemas()
        return self._schemas

    def ask(self, text, on_status=lambda s: None):
        cfg = config.load()
        ctx = tools.Context(cfg, self.confirm)
        self.history.append({"role": "user", "content": text})
        # Garde l'historique en mémoire borné (seule la fin est envoyée au modèle de toute façon).
        if len(self.history) > 4 * MAX_HISTORY:
            self.history = self._trimmed()
        # Instructions calculées UNE fois par demande : un préfixe identique d'une étape à l'autre
        # permet à Ollama de réutiliser son cache (pas de re-lecture de tout le prompt à chaque outil).
        system = {"role": "system", "content": self._system(cfg)}
        schemas = self._tool_schemas()
        for _ in range(MAX_STEPS):
            on_status("Réflexion…")
            msg = _post_chat(cfg, {
                "model": cfg["model"],
                "messages": [system] + self._trimmed(),
                "tools": schemas,
                "stream": False,
                "options": {"temperature": 0.2},
            })
            calls = msg.get("tool_calls") or []
            entry = {"role": "assistant", "content": msg.get("content", "")}
            if calls:
                entry["tool_calls"] = calls
            self.history.append(entry)
            if not calls:
                memory.save_conversation(self.history)
                return msg.get("content", "").strip() or "(pas de réponse)"
            errors = 0
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = _salvage_args(fn.get("arguments"))
                on_status(f"⚙ {tools.REGISTRY.get(name, {}).get('label', name)}…")
                result = tools.run(name, args, ctx)
                low = result.lower()
                if (result.startswith("Erreur") or low.startswith(("aucun", "rien trouvé"))
                        or "introuvable" in low):
                    errors += 1
                try:
                    memory.record_usage(name, args, result)
                except Exception:
                    pass
                self.history.append({"role": "tool", "content": result, "tool_name": name})
            # Si tout a échoué, souffle une piste pour que le modèle change d'approche au lieu de boucler.
            if errors and errors == len(calls):
                self.history.append({"role": "user", "content":
                                     "(note interne : l'outil a échoué. Change d'approche — autres mots-clés, "
                                     "nom anglais, autre outil — ou explique brièvement à l'utilisateur pourquoi "
                                     "ce n'est pas possible. Ne refais pas exactement le même appel.)"})
        return ("Je n'ai pas réussi à aller au bout de cette demande. Peux-tu me la reformuler, "
                "ou me donner un détail en plus ?")


def classify_notifications(items, time_budget=8):
    """Trie des notifications en importantes / pas importantes (en place).
    1) règles apprises (instantané)  2) IA locale, au plus `time_budget` s  3) sinon tri par mots-clés.
    Garantit qu'une notification s'affiche en moins de 15 s même si Ollama est occupé."""
    if not items:
        return items
    pending = []
    rules = notifications.learned_rules()
    for i in items:
        rule = notifications.learned_rule(i, rules)
        if rule is None:
            pending.append(i)
        else:
            i["important"], i["reason"] = rule, "règle apprise"
    items_all, items = items, pending
    if not items:
        return items_all
    cfg = config.load()
    deadline = time.monotonic() + time_budget
    rules = memory.prompt_block()
    system = (
        "Tu tries les notifications de l'utilisateur. IMPORTANT = un humain lui écrit directement "
        "(message privé, mention @, réponse), un proche ou contact connu, travail/école, argent ou sécurité "
        "(code, paiement, connexion suspecte), rendez-vous, livraison, urgence. PAS IMPORTANT = promos, "
        "newsletters, mises à jour, suggestions, jeux, réseaux sociaux génériques, messages de serveurs sans mention. "
        "Les règles « [notif] » ci-dessous sont prioritaires sur tout le reste.\n\n" + rules
    )
    for start in range(0, len(items), 15):
        chunk = items[start:start + 15]
        lines = "\n".join(f"{i['id']} | {i['app']} | {i['title']} | {i['body'][:200]}" for i in chunk)
        remaining = deadline - time.monotonic()
        try:
            if remaining < 1:
                raise TimeoutError
            msg = _post_chat(cfg, {
                "model": cfg["model"], "stream": False, "format": "json",
                "options": {"temperature": 0},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content":
                              'Réponds uniquement en JSON : {"resultats":[{"id":<id>,"important":true ou false,'
                              '"raison":"<5 mots max>"}]}\n\nNotifications (id | app | titre | texte) :\n' + lines}],
            }, timeout=remaining)
            res = {int(r["id"]): r for r in json.loads(msg.get("content", "{}")).get("resultats", [])
                   if str(r.get("id", "")).lstrip("-").isdigit()}
        except Exception:
            res = {}
        for i in chunk:
            r = res.get(i["id"])
            if r is None:
                notifications.heuristic(i)
            else:
                i["important"] = bool(r.get("important"))
                i["reason"] = str(r.get("raison", ""))[:60]
    return items_all


def model_installed(cfg=None, model=None):
    """True / False, ou None si Ollama est injoignable."""
    cfg = cfg or config.load()
    model = model or cfg["model"]
    models = _installed_models(cfg)
    if models is None:
        return None
    return any(_same_model(m, model) for m in models)


def pull_model(model, on_status=lambda s: None, cfg=None):
    """Télécharge un modèle via Ollama en montrant la progression. Renvoie (ok, message)."""
    cfg = cfg or config.load()
    url = _base_url(cfg) + "/api/pull"
    try:
        with requests.post(url, json={"model": model, "stream": True}, stream=True, timeout=3600) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                if data.get("error"):
                    return False, data["error"]
                status = data.get("status", "")
                total, done = data.get("total"), data.get("completed")
                if total and done:
                    on_status(f"Téléchargement de {model} : {done * 100 // total} %")
                elif status:
                    on_status(status)
        return True, f"{model} est prêt."
    except Exception as e:
        return False, f"Échec du téléchargement : {e}"


def check_ollama():
    """Renvoie None si tout va bien, sinon un message d'aide."""
    cfg = config.load()
    models = _installed_models(cfg)
    if models is None:
        return "⚠ Ollama ne semble pas lancé. Installe-le depuis ollama.com, lance-le, puis relance Cronux."
    want = cfg["model"]
    if not any(_same_model(m, want) for m in models):
        return f"⚠ Le modèle « {want} » n'est pas installé. Ouvre un terminal et tape :\nollama pull {want}"
    return None
