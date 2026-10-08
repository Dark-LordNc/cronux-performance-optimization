# cronux-performance-optimization
Performance optimization analysis and improvements for Cronux AI assistant

## Contenu

| Chemin | Rôle |
|---|---|
| `src/` | Les 15 modules de Cronux (ce qui est embarqué dans `Cronux.pyw`) |
| `launcher.py` | Le lanceur auto-extractible (modèle, sans les modules) |
| `build.py` | Reconstruit le fichier unique : `python build.py` → `dist/Cronux.pyw` |
| `dist/Cronux.pyw` | Le Cronux prêt à l'emploi : remplace l'ancien fichier par celui-ci |
| `tests/` | Tests automatiques (pytest) + `bench.py` (mesures de performance) |

## Tester

```bash
pip install customtkinter requests spotipy psutil pillow pytest
python -m pytest tests/                 # sous Linux sans écran : xvfb-run -a python -m pytest tests/
python tests/bench.py                   # mesures ; python tests/bench.py <autre_dossier_src> pour comparer
```

Les tests utilisent un `APPDATA` temporaire, un faux serveur Ollama et une fausse base de notifications
Windows : ils ne touchent jamais à la vraie configuration.

## 1.9.2 — performances et corrections

**Performances** (mesuré avec `tests/bench.py`, 1.9.1 → 1.9.2)

| Chemin | Avant | Après |
|---|---|---|
| `config.load()` (appelé toutes les 4 s par la surveillance) | 455 µs + réécriture du fichier | 16 µs, aucune écriture |
| Règles apprises pour un lot de 15 notifications | 3 192 µs | 41 µs |
| Badge 🔔 (`unseen_important`) | 535 µs | 13 µs |
| Instructions de l'IA (`prompt_block`) | 175 µs | 32 µs |
| Redimensionner la fenêtre (100 bulles) | 49 187 reconfigurations, 4,3 s figée | 102, 0,2 s |
| Recherche dans 72 Mo de fichiers de jeu | 254 ms, fichier entier en RAM (jusqu'à 128 Mo) | 218 ms, morceaux de 4 Mo |

En plus :
- **Ollama :**
  - la connexion HTTP est réutilisée (keep-alive) ;
  - les instructions sont identiques d'une étape à l'autre, ce qui permet à Ollama de réutiliser son cache.
- **Démarrage :** les dépendances sont vérifiées sans les importer.
- **Moins d'appels répétés :**
  - les raccourcis du menu Démarrer et le résultat de `nvidia-smi` sont gardés en cache ;
  - l'appareil Spotify est gardé en cache ;
  - le curseur de volume Spotify n'envoie plus des dizaines de requêtes.
- **Fenêtres plus légères :**
  - au maximum 150 bulles dans la conversation ;
  - au maximum 5 bulles de notification à l'écran.

**Corrections de bugs**
- **Mode Gaming :** une ligne vide dans « apps à fermer » fermait **tous** les processus du PC.
- **Entretien du PC :**
  - une erreur affichait un `NameError` au lieu du message ;
  - un dossier temporaire illisible faisait planter tout le nettoyage ;
  - les jonctions et les liens ne sont plus jamais suivis ;
  - le message « ✓ X libérés » s'effaçait aussitôt.
- **Discord :**
  - la 2ᵉ tentative de connexion échouait (« port déjà utilisé ») ;
  - la requête `/favicon.ico` du navigateur pouvait effacer le code reçu ;
  - « Se déconnecter » affichait encore « Connecté ».
- **`config.json` :**
  - réécrit à chaque lecture ;
  - un fichier abîmé effaçait tous les réglages (il est maintenant mis de côté en `.bak`) ;
  - les écritures sont atomiques.
- **Interface :**
  - les threads modifiaient directement les widgets Tk, ce qui n'est pas thread-safe : il y a maintenant une file d'actions sur le thread de l'interface ;
  - `confirm()` se bloquait à vie si on l'appelait depuis l'interface ;
  - les fenêtres Réglages et Discord se figeaient pendant les appels réseau.
- **Jeux :**
  - un jeu installé dans un « dossier de jeux supplémentaire » ajouté avec le bouton n'était jamais reconnu (`D:/Jeux` contre `D:\Jeux`) ;
  - un dossier protégé faisait planter la recherche ;
  - le délai de 45 s n'arrêtait pas la recherche dans les dossiers suivants.
- **Recherche de fichiers :** le délai de 15 s n'arrêtait pas le parcours des dossiers suivants.
- **Matériel :** une valeur « [N/A] » de `nvidia-smi` faisait planter l'état du GPU.
- **Ollama :** « qwen2.5 » était vu comme installé alors que seul « qwen2.5:14b » l'était. Un délai dépassé affiche maintenant un message clair.
- **Outils :**
  - un argument inventé par le modèle faisait échouer l'outil ;
  - une erreur interne était présentée comme une « erreur d'arguments ».
- **Spotify :** un nouveau Client ID n'était pris en compte qu'après redémarrage.
- **Mails :** les ids d'e-mails changeaient d'une liste à l'autre, et leur nombre grossissait sans limite.
- **Lanceur :**
  - une erreur au démarrage était invisible avec `pythonw` : elle s'affiche maintenant et est enregistrée dans `erreur_demarrage.txt` ;
  - si l'installation des dépendances échoue, il réessaie avec `pip --user`.
