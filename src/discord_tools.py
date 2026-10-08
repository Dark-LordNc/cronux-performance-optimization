"""Discord via un bot officiel (optionnel). Les messages reçus sur ton compte passent par les notifications.

Pourquoi un bot et pas ton compte : Discord interdit d'automatiser un compte utilisateur
(« selfbot ») et bannit les comptes qui le font."""
import requests

from tools import ToolError, _open, tool

API = "https://discord.com/api/v10"
_CACHE = {"channels": None}


def _req(ctx, method, path, **kw):
    token = ctx.config.get("discord_bot_token", "").strip()
    if not token:
        raise ToolError("Pour lire ou écrire dans tes serveurs, il faut configurer un bot Discord "
                        "(gratuit, 5 min, voir LISEZMOI) puis coller son token dans les réglages ⚙. "
                        "Les messages que tu reçois restent visibles via les notifications.")
    r = requests.request(method, API + path, headers={"Authorization": f"Bot {token}"}, timeout=15, **kw)
    if r.status_code == 401:
        raise ToolError("Le token du bot Discord est invalide.")
    if r.status_code == 403:
        raise ToolError("Le bot n'a pas la permission pour ça (vérifie ses rôles sur le serveur).")
    r.raise_for_status()
    return r.json() if r.content else {}


def send_file(ctx, channel, file_path, message=""):
    """Envoie un fichier (ex. une capture d'écran) dans un salon Discord via le bot."""
    import os
    token = ctx.config.get("discord_bot_token", "").strip()
    if not token:
        raise ToolError("Il faut configurer le bot Discord (⚙ → connexion Discord) pour envoyer un fichier.")
    if not os.path.exists(file_path):
        raise ToolError(f"Fichier introuvable : {file_path}")
    c = _find_channel(ctx, channel)
    with open(file_path, "rb") as fh:
        files = {"files[0]": (os.path.basename(file_path), fh, "application/octet-stream")}
        data = {"payload_json": __import__("json").dumps({"content": message[:2000]})}
        r = requests.post(f"{API}/channels/{c['id']}/messages",
                          headers={"Authorization": f"Bot {token}"}, data=data, files=files, timeout=60)
    if r.status_code == 403:
        raise ToolError("Le bot n'a pas la permission d'envoyer dans ce salon.")
    r.raise_for_status()
    return f"Fichier envoyé dans #{c['name']}."


def _channels(ctx):
    if _CACHE["channels"] is None:
        out = []
        for g in _req(ctx, "GET", "/users/@me/guilds"):
            for c in _req(ctx, "GET", f"/guilds/{g['id']}/channels"):
                if c.get("type") in (0, 5):  # salons texte / annonces
                    out.append({"id": c["id"], "name": c["name"], "guild": g["name"], "guild_id": g["id"]})
        _CACHE["channels"] = out
    return _CACHE["channels"]


def _find_channel(ctx, name):
    q = name.lower().replace("#", "").strip()
    guild_q = None
    if "/" in q:
        guild_q, q = [p.strip() for p in q.split("/", 1)]
    chans = [c for c in _channels(ctx) if not guild_q or guild_q in c["guild"].lower()]
    exact = [c for c in chans if c["name"].lower() == q]
    partial = [c for c in chans if q in c["name"].lower()]
    found = exact or partial
    if not found:
        names = ", ".join(f"{c['guild']}/#{c['name']}" for c in chans[:25])
        raise ToolError(f"Salon « {name} » introuvable. Salons disponibles : {names}")
    return found[0]


@tool("discord_open", "Ouvre l'application Discord.", label="J'ouvre Discord")
def discord_open(ctx):
    _open("discord:")
    return "Discord ouvert."


@tool("discord_channels", "Liste les serveurs et salons Discord accessibles au bot.",
      label="Je regarde tes serveurs Discord")
def discord_channels(ctx):
    _CACHE["channels"] = None
    chans = _channels(ctx)
    if not chans:
        return "Le bot n'est sur aucun serveur. Invite-le d'abord (voir LISEZMOI)."
    return "\n".join(f"- {c['guild']} › #{c['name']}" for c in chans)


@tool("discord_read", "Lit les derniers messages d'un salon Discord (format 'salon' ou 'serveur/salon').",
      {"channel": {"type": "string"}, "count": {"type": "integer", "description": "défaut 15"}},
      required=["channel"], label="Je lis le salon Discord")
def discord_read(ctx, channel, count=15):
    c = _find_channel(ctx, channel)
    msgs = _req(ctx, "GET", f"/channels/{c['id']}/messages", params={"limit": min(int(count or 15), 50)})
    lines = []
    for m in reversed(msgs):
        content = m.get("content") or ("(pièce jointe)" if m.get("attachments") else
                                       "(contenu masqué : active « Message Content Intent » sur le bot)")
        lines.append(f"{m['timestamp'][:16].replace('T', ' ')} {m['author'].get('global_name') or m['author']['username']} : {content}")
    return f"#{c['name']} ({c['guild']})\n" + "\n".join(lines) if lines else "Aucun message."


@tool("discord_send", "Envoie un message dans un salon Discord avec le bot (confirmation demandée).",
      {"channel": {"type": "string"}, "message": {"type": "string"}},
      required=["channel", "message"], label="Je prépare le message Discord")
def discord_send(ctx, channel, message):
    c = _find_channel(ctx, channel)
    if not ctx.ask("Envoyer sur Discord ?", f"{c['guild']} › #{c['name']}\n\n{message}"):
        return "L'utilisateur a annulé l'envoi."
    _req(ctx, "POST", f"/channels/{c['id']}/messages", json={"content": message[:2000]})
    return f"Message envoyé dans #{c['name']}."


@tool("discord_dm", "Envoie un message privé Discord via le bot à un membre d'un de tes serveurs "
                    "(confirmation demandée).",
      {"user": {"type": "string", "description": "Pseudo de la personne"}, "message": {"type": "string"}},
      required=["user", "message"], label="Je prépare le MP Discord")
def discord_dm(ctx, user, message):
    member = None
    for g in _req(ctx, "GET", "/users/@me/guilds"):
        res = _req(ctx, "GET", f"/guilds/{g['id']}/members/search", params={"query": user, "limit": 1})
        if res:
            member = res[0]["user"]
            break
    if not member:
        raise ToolError(f"Je ne trouve pas « {user} » sur les serveurs du bot.")
    who = member.get("global_name") or member["username"]
    if not ctx.ask("Envoyer ce MP Discord ?", f"À : {who}\n\n{message}"):
        return "L'utilisateur a annulé l'envoi."
    dm = _req(ctx, "POST", "/users/@me/channels", json={"recipient_id": member["id"]})
    _req(ctx, "POST", f"/channels/{dm['id']}/messages", json={"content": message[:2000]})
    return f"MP envoyé à {who} (depuis le bot)."
