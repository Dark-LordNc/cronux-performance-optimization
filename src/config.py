"""Configuration de Cronux (stockée dans %APPDATA%\\Cronux\\config.json)."""
import json
import os

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Cronux")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "ollama_url": "http://localhost:11434",
    "model": "qwen2.5:14b",
    "user_name": "",
    "spotify_client_id": "",
    "spotify_redirect_uri": "http://127.0.0.1:8888/callback",
    "search_folders": [],
    "confirm_actions": True,
    "context_tokens": 16384,
    "notif_watch": True,
    "notif_sound": True,
    "notif_bubble": True,
    "notif_check_seconds": 4,
    "keep_model_loaded_minutes": 60,
    "discord_client_id": "",
    "discord_client_secret": "",
    "discord_bot_token": "",
    "game_folders": [],
    "update_url": "",
    "start_with_windows": False,
    "gaming_close": [],
}


# Description des réglages, pour la fenêtre intégrée (ordre d'affichage).
# type : text / password / bool / int / folders
FIELDS = [
    ("user_name", "Ton prénom", "text", "Pour que Cronux t'appelle par ton nom.", ""),
    ("model", "Modèle Ollama", "text", "Ex. qwen2.5:7b, ou qwen2.5:3b sur un PC modeste.", ""),
    ("spotify_client_id", "Spotify — Client ID", "password",
     "Contrôle complet de Spotify (Premium). Clique « Comment l'obtenir ».", "spotify"),
    ("discord_bot_token", "Discord — Connexion", "button",
     "« Se connecter avec Discord » + bot pour lire/écrire dans tes serveurs.", "discord"),
    ("notif_watch", "Surveiller les notifications", "bool",
     "Lire et trier les notifications Windows (Discord, mails…).", ""),
    ("notif_sound", "Son à la réception", "bool",
     "Petit son quand un message Discord arrive, sonnerie différente pour un appel.", ""),
    ("notif_bubble", "Bulles flottantes", "bool",
     "Affiche les messages Discord (et notifs importantes) en bulle en bas de l'écran.", ""),
    ("notif_check_seconds", "Fréquence des notifs (s)", "int",
     "Toutes les combien de secondes vérifier (4 recommandé, affichage en < 15 s).", ""),
    ("confirm_actions", "Confirmer avant d'envoyer", "bool",
     "Demander avant chaque mail, rendez-vous ou message Discord.", ""),
    ("context_tokens", "Mémoire de travail (tokens)", "int",
     "16384 par défaut. Baisse à 8192 si le PC rame.", ""),
    ("keep_model_loaded_minutes", "Garder le modèle chargé (min)", "int",
     "Évite un rechargement lent du modèle entre deux demandes.", ""),
    ("search_folders", "Dossiers où chercher tes fichiers", "folders",
     "Vide = Bureau, Documents, Téléchargements, Images, Musique, Vidéos, OneDrive.", ""),
    ("game_folders", "Dossiers de jeux supplémentaires", "folders",
     "Ex. D:\\Jeux, si tes jeux ne sont pas sur le disque C.", ""),
    ("start_with_windows", "Démarrer avec Windows", "bool",
     "Lancer Cronux automatiquement au démarrage du PC.", ""),
    ("gaming_close", "Mode Gaming : apps à fermer en plus", "folders",
     "Noms d'apps supplémentaires à fermer en Mode Gaming (une par ligne, ex. obs64).", ""),
    ("update_url", "Adresse de mise à jour (avancé)", "text",
     "Optionnel. JSON {version, url, sha256} pour les mises à jour en ligne.", ""),
    ("ollama_url", "Adresse d'Ollama (avancé)", "text",
     "http://localhost:11434 par défaut.", ""),
]

# Modèles conseillés. label → (tag Ollama, description). Adaptés à 16 Go de RAM + GPU NVIDIA.
MODEL_PRESETS = [
    ("Intelligent (recommandé)", "qwen2.5:14b", "Le plus malin pour comprendre et enchaîner les actions. Idéal avec ton GPU NVIDIA."),
    ("Rapide", "qwen2.5:7b", "Très réactif, un peu moins fin. Bon si tu veux des réponses instantanées."),
    ("Léger", "qwen2.5:3b", "Pour les PC modestes ou sans carte graphique."),
]

HELP_LINKS = {
    "spotify": ("https://developer.spotify.com/dashboard",
                "1. Crée une app sur le dashboard Spotify.\n"
                "2. Redirect URI : http://127.0.0.1:8888/callback — coche « Web API ».\n"
                "3. Copie le Client ID et colle-le ici.\n"
                "(Spotify Premium requis pour lancer un titre précis.)"),
    "discord": ("https://discord.com/developers/applications",
                "Une seule app Discord fournit tout. Sur https://discord.com/developers/applications :\n"
                "1. New Application. Dans « OAuth2 » : copie le Client ID et le Client Secret,\n"
                "   et AJOUTE le Redirect http://127.0.0.1:53110/callback (puis Save).\n"
                "2. Onglet « Bot » → Reset Token (pour lire/écrire dans les serveurs),\n"
                "   active « Message Content Intent » et « Server Members Intent ».\n"
                "Ensuite, dans Cronux : clique « Se connecter avec Discord »."),
}


def load() -> dict:
    os.makedirs(APP_DIR, exist_ok=True)
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    # Ajoute les clés manquantes pour que l'utilisateur les voie dans le fichier
    save(cfg)
    return cfg


def update(changes: dict) -> dict:
    cfg = load()
    cfg.update(changes)
    save(cfg)
    return cfg


def save(cfg: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
