"""Cronux — fenêtre principale."""
import datetime
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

import config
import memory
import tools
import maintenance
import hardware
import gaming  # noqa: F401
import startup
import discord_auth
import notifications
import sounds
from version import VERSION
import agent as agent_mod
from agent import Agent, check_ollama, classify_notifications

# ── Thème Cronux (sombre, accent indigo ; le logo reste identique) ──
ACCENT = "#6366F1"        # indigo
ACCENT_HOVER = "#4F46E5"
USER_COLOR = ("#6366F1", "#4F46E5")
BOT_COLOR = ("#EDEDF2", "#23252E")
NOTIF_COLOR = ("#FDE68A", "#4A3F12")
CARD_COLOR = ("#F4F4F8", "#1C1E26")


def _apply_theme():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    try:
        t = ctk.ThemeManager.theme
        t["CTkButton"]["fg_color"] = [ACCENT, ACCENT]
        t["CTkButton"]["hover_color"] = [ACCENT_HOVER, ACCENT_HOVER]
        t["CTkSwitch"]["progress_color"] = [ACCENT, ACCENT]
        t["CTkSlider"]["button_color"] = [ACCENT, ACCENT]
        t["CTkSlider"]["button_hover_color"] = [ACCENT_HOVER, ACCENT_HOVER]
        t["CTkCheckBox"]["fg_color"] = [ACCENT, ACCENT]
        t["CTkCheckBox"]["hover_color"] = [ACCENT_HOVER, ACCENT_HOVER]
        t["CTkEntry"]["border_color"] = [ACCENT, ACCENT]
        t["CTkOptionMenu"]["fg_color"] = [ACCENT, ACCENT]
        t["CTkOptionMenu"]["button_color"] = [ACCENT_HOVER, ACCENT_HOVER]
        t["CTkOptionMenu"]["button_hover_color"] = [ACCENT_HOVER, ACCENT_HOVER]
        t["CTkFrame"]["top_fg_color"] = ["#15161C", "#15161C"]
        t["CTkFrame"]["fg_color"] = ["#101117", "#101117"]
        if "CTk" in t:
            t["CTk"]["fg_color"] = ["#0C0D12", "#0C0D12"]
    except Exception:
        pass


_apply_theme()


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _open_file(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])


def _short_time(t):
    try:
        return datetime.datetime.strptime(t, "%Y-%m-%d %H:%M").strftime("%d/%m %H:%M")
    except Exception:
        return t


class NotifPanel(ctk.CTkToplevel):
    """Fenêtre des notifications triées. Corriger le tri apprend une règle à Cronux."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Notifications — Cronux")
        self.geometry("420x580")
        self.transient(app)
        self.tab = ctk.CTkSegmentedButton(self, values=["Importantes", "Autres"],
                                          command=lambda _: self.refresh())
        self.tab.set("Importantes")
        self.tab.pack(fill="x", padx=12, pady=(12, 6))
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list.pack(fill="both", expand=True, padx=8)
        ctk.CTkLabel(self, text="Corrige le tri si besoin : Cronux retient tes choix.",
                     text_color="gray").pack(pady=(4, 10))
        self.refresh()
        notifications.mark_all_seen()
        app.update_badge()
        self.after(150, self.focus_force)

    def refresh(self):
        for w in self.list.winfo_children():
            w.destroy()
        important = self.tab.get() == "Importantes"
        items = notifications.recent(only_important=important, count=60)
        if not items:
            ctk.CTkLabel(self.list, text="Rien ici pour l'instant.", text_color="gray").pack(pady=30)
            return
        for n in items:
            card = ctk.CTkFrame(self.list, fg_color=CARD_COLOR, corner_radius=10)
            card.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(card, text=f"{n['app']} · {_short_time(n['time'])}", text_color="gray",
                         font=ctk.CTkFont(size=11), anchor="w").pack(fill="x", padx=10, pady=(6, 0))
            ctk.CTkLabel(card, text=n["title"], font=ctk.CTkFont(weight="bold"), anchor="w",
                         justify="left", wraplength=330).pack(fill="x", padx=10)
            if n["body"]:
                ctk.CTkLabel(card, text=n["body"], anchor="w", justify="left",
                             wraplength=330).pack(fill="x", padx=10)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=(2, 8))
            if n.get("reason"):
                ctk.CTkLabel(row, text=n["reason"], text_color="gray",
                             font=ctk.CTkFont(size=11, slant="italic")).pack(side="left")
            ctk.CTkButton(row, text="Pas important" if important else "★ Important", width=110, height=26,
                          fg_color="transparent", border_width=1, text_color=("black", "white"),
                          command=lambda n=n, imp=not important: self.reclass(n, imp)).pack(side="right")

    def reclass(self, n, important):
        notifications.set_importance(n["id"], important)
        memory.remember(None, f"[notif] Les notifications de {n['app']} « {n['title'][:60]} » "
                              f"{'sont importantes' if important else 'ne sont pas importantes'}")
        self.refresh()


class SettingsPanel(ctk.CTkToplevel):
    """Réglages directement dans Cronux : plus besoin d'ouvrir un fichier .json."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Réglages — Cronux")
        self.geometry("560x640")
        self.transient(app)
        self.cfg = config.load()
        self.vars = {}

        ctk.CTkLabel(self, text="Réglages", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 2))
        ctk.CTkLabel(self, text="Les boutons « Comment l'obtenir » ouvrent la bonne page et expliquent les étapes.",
                     text_color="gray", wraplength=520).pack(pady=(0, 6))
        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=12, pady=4)

        for key, label, kind, help_text, link_key in config.FIELDS:
            row = ctk.CTkFrame(body, fg_color=CARD_COLOR, corner_radius=10)
            row.pack(fill="x", pady=5, padx=4)
            head = ctk.CTkFrame(row, fg_color="transparent")
            head.pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(head, text=label, font=ctk.CTkFont(weight="bold"), anchor="w").pack(side="left")
            if link_key:
                ctk.CTkButton(head, text="Comment l'obtenir", width=130, height=24,
                              command=lambda k=link_key: self._help(k)).pack(side="right")
            ctk.CTkLabel(row, text=help_text, text_color="gray", anchor="w",
                         justify="left", wraplength=480).pack(fill="x", padx=10)
            val = self.cfg.get(key)
            if key == "discord_bot_token":
                ctk.CTkButton(row, text="Ouvrir la connexion Discord…",
                              command=self.app.open_discord).pack(anchor="w", padx=10, pady=(2, 8))
                continue
            if key == "model":
                labels = [p[0] for p in config.MODEL_PRESETS] + ["Autre (personnalisé)"]
                tag_by_label = {p[0]: p[1] for p in config.MODEL_PRESETS}
                cur_label = next((p[0] for p in config.MODEL_PRESETS if p[1] == val), "Autre (personnalisé)")
                sel = ctk.StringVar(value=cur_label)
                custom = ctk.StringVar(value="" if cur_label != "Autre (personnalisé)" else str(val or ""))
                desc = ctk.CTkLabel(row, text="", text_color="gray", anchor="w", justify="left", wraplength=480)
                entry = ctk.CTkEntry(row, textvariable=custom, placeholder_text="ex. qwen2.5:14b")

                def _on_model(choice, d=desc, e=entry):
                    info = next((p[2] for p in config.MODEL_PRESETS if p[0] == choice), "Tag Ollama exact à utiliser.")
                    d.configure(text=info)
                    if choice == "Autre (personnalisé)":
                        e.pack(fill="x", padx=10, pady=(0, 8))
                    else:
                        e.pack_forget()
                ctk.CTkOptionMenu(row, values=labels, variable=sel, command=_on_model).pack(
                    anchor="w", padx=10, pady=(2, 2))
                desc.pack(fill="x", padx=10)
                _on_model(cur_label)
                self.vars[key] = ("model", (sel, custom, tag_by_label))
                continue
            if kind == "bool":
                v = ctk.BooleanVar(value=bool(val))
                ctk.CTkSwitch(row, text="", variable=v, width=40).pack(anchor="w", padx=10, pady=(2, 8))
            elif kind == "folders":
                v = ctk.StringVar(value="\n".join(val or []))
                box = ctk.CTkTextbox(row, height=54)
                box.insert("1.0", v.get())
                box.pack(fill="x", padx=10, pady=(2, 2))
                ctk.CTkButton(row, text="+ Ajouter un dossier…", width=160, height=24,
                              command=lambda b=box: self._add_folder(b)).pack(anchor="w", padx=10, pady=(0, 8))
                self.vars[key] = ("folders", box)
                continue
            else:
                show = "•" if kind == "password" else None
                v = ctk.StringVar(value="" if val is None else str(val))
                ctk.CTkEntry(row, textvariable=v, show=show).pack(fill="x", padx=10, pady=(2, 8))
            self.vars[key] = (kind, v)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=10)
        self.saved = ctk.CTkLabel(bar, text="", text_color="#15803d")
        self.saved.pack(side="left")
        ctk.CTkButton(bar, text="Enregistrer", command=self.save).pack(side="right")
        self.after(150, self.focus_force)

    def _help(self, link_key):
        url, steps = config.HELP_LINKS[link_key]
        webbrowser.open(url)
        messagebox.showinfo("Comment l'obtenir", steps + f"\n\nPage ouverte : {url}", parent=self)

    def _add_folder(self, box):
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self, title="Choisis un dossier")
        if path:
            cur = box.get("1.0", "end").strip()
            box.delete("1.0", "end")
            box.insert("1.0", (cur + "\n" + path).strip() if cur else path)

    def save(self):
        changes = {}
        for key, (kind, widget) in self.vars.items():
            if kind == "model":
                sel, custom, tag_by_label = widget
                choice = sel.get()
                changes[key] = tag_by_label.get(choice) or str(custom.get()).strip() or self.cfg.get("model")
            elif kind == "bool":
                changes[key] = bool(widget.get())
            elif kind == "folders":
                changes[key] = [l.strip() for l in widget.get("1.0", "end").splitlines() if l.strip()]
            elif kind == "int":
                try:
                    changes[key] = int(str(widget.get()).strip() or 0)
                except ValueError:
                    continue
            else:
                changes[key] = str(widget.get()).strip()
        config.update(changes)
        if "start_with_windows" in changes:
            try:
                startup.set_enabled(bool(changes["start_with_windows"]))
            except Exception:
                pass
        self.saved.configure(text="Enregistré ✓  (pris en compte immédiatement)")
        self.after(2500, lambda: self.saved.configure(text=""))
        # Si le modèle choisi n'est pas encore téléchargé, propose de le faire maintenant.
        model = changes.get("model")
        if model and agent_mod.model_installed(model=model) is False:
            if messagebox.askyesno("Modèle à télécharger",
                                   f"Le modèle « {model} » n'est pas encore installé.\n"
                                   "Le télécharger maintenant ? (plusieurs Go, une seule fois)", parent=self):
                threading.Thread(target=self._pull, args=(model,), daemon=True).start()

    def _pull(self, model):
        self.saved.configure(text_color="#2563EB")
        ok, msg = agent_mod.pull_model(model, on_status=lambda s: self.saved.configure(text=s))
        self.saved.configure(text=("✓ " if ok else "⚠ ") + msg, text_color="#15803d" if ok else "#b91c1c")


class MemoryPanel(ctk.CTkToplevel):
    """Ce que Cronux sait sur toi, modifiable directement : plus besoin d'ouvrir un fichier .json."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Mémoire — Cronux")
        self.geometry("520x600")
        self.transient(app)

        ctk.CTkLabel(self, text="🧠 Ce que Cronux sait sur toi",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 2))
        add = ctk.CTkFrame(self, fg_color="transparent")
        add.pack(fill="x", padx=12, pady=6)
        self.entry = ctk.CTkEntry(add, placeholder_text="Ajouter un souvenir (ex. Ma sœur = lea@mail.com)")
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self._add())
        ctk.CTkButton(add, text="+", width=40, command=self._add).pack(side="left", padx=(6, 0))

        self.list = ctk.CTkScrollableFrame(self, label_text="Souvenirs")
        self.list.pack(fill="both", expand=True, padx=8, pady=4)
        self.habits = ctk.CTkScrollableFrame(self, label_text="Habitudes observées", height=140)
        self.habits.pack(fill="x", padx=8, pady=(0, 10))
        self.refresh()
        self.after(150, self.focus_force)

    def refresh(self):
        for w in self.list.winfo_children():
            w.destroy()
        facts = memory.all_facts()
        if not facts:
            ctk.CTkLabel(self.list, text="Rien encore. Cronux apprendra en discutant avec toi.",
                         text_color="gray").pack(pady=20)
        for f in reversed(facts):
            row = ctk.CTkFrame(self.list, fg_color=CARD_COLOR, corner_radius=8)
            row.pack(fill="x", pady=3, padx=4)
            ctk.CTkLabel(row, text=f["text"], anchor="w", justify="left",
                         wraplength=410).pack(side="left", fill="x", expand=True, padx=10, pady=6)
            ctk.CTkButton(row, text="🗑", width=34, fg_color="transparent", border_width=1,
                          text_color=("black", "white"),
                          command=lambda i=f["id"]: self._del(i)).pack(side="right", padx=6)
        for w in self.habits.winfo_children():
            w.destroy()
        hs = memory.habits_summary()
        if not hs:
            ctk.CTkLabel(self.habits, text="Aucune habitude encore.", text_color="gray").pack(pady=10)
        for h in hs:
            ctk.CTkLabel(self.habits, text="• " + h, anchor="w", justify="left",
                         wraplength=460).pack(fill="x", padx=10, pady=1)

    def _add(self):
        text = self.entry.get().strip()
        if text:
            memory.add_fact(text)
            self.entry.delete(0, "end")
            self.refresh()

    def _del(self, fact_id):
        memory.delete_fact(fact_id)
        self.refresh()


class Overlay(ctk.CTkToplevel):
    """Petit affichage par-dessus le jeu (heure, GPU, prochain rdv). Fonctionne au-dessus des jeux en
    fenêtré/fenêtré sans bordure ; pas au-dessus du plein écran exclusif (limite de Windows)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.82)
        except Exception:
            pass
        self.configure(fg_color="#0b0b0b")
        self.label = ctk.CTkLabel(self, text="…", justify="left", font=ctk.CTkFont(size=13),
                                  text_color="#e5e7eb")
        self.label.pack(padx=12, pady=8)
        # Coin haut-droit
        self.update_idletasks()
        x = self.winfo_screenwidth() - 230
        self.geometry(f"220x74+{x}+16")
        # Déplaçable à la souris
        for w in (self, self.label):
            w.bind("<Button-1>", self._start)
            w.bind("<B1-Motion>", self._drag)
        self._alive = True
        self._tick()

    def _start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag(self, e):
        self.geometry(f"+{self.winfo_pointerx() - self._dx}+{self.winfo_pointery() - self._dy}")

    def _tick(self):
        if not self._alive:
            return
        threading.Thread(target=self._refresh, daemon=True).start()
        self.after(3000, self._tick)

    def _refresh(self):
        text = datetime.datetime.now().strftime("%H:%M")
        try:
            gpus = hardware.gpu_status()
            if gpus and gpus[0].get("util") is not None:
                g = gpus[0]
                text += f"   GPU {g['util']:.0f}%  {g['temp']:.0f}°C"
        except Exception:
            pass
        if self._alive:
            self.after(0, lambda: self.label.configure(text=text))

    def close(self):
        self._alive = False
        try:
            self.destroy()
        except Exception:
            pass


class GamingPanel(ctk.CTkToplevel):
    """⚡ Gaming & PC : mode gaming, surveillance matériel en direct, overlay, capture + partage."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Gaming & PC — Cronux")
        self.geometry("420x520")
        self.transient(app)
        self.ctx = tools.Context(config.load(), app.confirm)

        ctk.CTkLabel(self, text="⚡ Gaming & PC", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 6))

        gm = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=10)
        gm.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(gm, text="Mode Gaming", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(gm, text="Ferme les apps gourmandes pour gagner des FPS, puis les relance.",
                     text_color="gray", anchor="w", justify="left", wraplength=360).pack(fill="x", padx=10)
        gmb = ctk.CTkFrame(gm, fg_color="transparent")
        gmb.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(gmb, text="▶ Activer", command=lambda: self._gaming("on")).pack(side="left")
        ctk.CTkButton(gmb, text="■ Désactiver", fg_color="transparent", border_width=1,
                      text_color=("black", "white"), command=lambda: self._gaming("off")).pack(side="left", padx=8)

        hw = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=10)
        hw.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(hw, text="Surveillance matériel", font=ctk.CTkFont(weight="bold"),
                     anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.hw = ctk.CTkLabel(hw, text="…", anchor="w", justify="left", font=ctk.CTkFont(size=13))
        self.hw.pack(fill="x", padx=10, pady=(0, 8))

        ov = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=10)
        ov.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(ov, text="Overlay en jeu", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(ov, text="Petite info (heure, GPU) par-dessus le jeu. Fonctionne en fenêtré / fenêtré "
                             "sans bordure, pas en plein écran exclusif.",
                     text_color="gray", anchor="w", justify="left", wraplength=360).pack(fill="x", padx=10)
        ctk.CTkButton(ov, text="Afficher / masquer l'overlay", command=self.app.toggle_overlay).pack(
            anchor="w", padx=10, pady=8)

        sc = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=10)
        sc.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(sc, text="Capture d'écran", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        scb = ctk.CTkFrame(sc, fg_color="transparent")
        scb.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(scb, text="📸 Capturer", command=self._shot).pack(side="left")
        self.chan = ctk.CTkEntry(scb, placeholder_text="salon Discord", width=140)
        self.chan.pack(side="left", padx=8)
        ctk.CTkButton(scb, text="Envoyer", width=70, command=self._shot_discord).pack(side="left")

        self.msg = ctk.CTkLabel(self, text="", text_color="gray", wraplength=380)
        self.msg.pack(pady=6)

        self._alive = True
        self._hw_tick()
        self.after(150, self.focus_force)

    def _gaming(self, state):
        self.msg.configure(text="…", text_color="gray")
        threading.Thread(target=lambda: self._set_msg(tools.run("gaming_mode", {"state": state}, self.ctx)),
                         daemon=True).start()

    def _shot(self):
        threading.Thread(target=lambda: self._set_msg(tools.run("screenshot", {}, self.ctx)), daemon=True).start()

    def _shot_discord(self):
        ch = self.chan.get().strip()
        if not ch:
            self.msg.configure(text="Indique un salon Discord.", text_color="#b91c1c")
            return
        threading.Thread(target=lambda: self._set_msg(
            tools.run("screenshot_to_discord", {"channel": ch}, self.ctx)), daemon=True).start()

    def _set_msg(self, text):
        if self._alive:
            self.after(0, lambda: self.msg.configure(text=text, text_color="gray"))

    def _hw_tick(self):
        if not self._alive:
            return
        threading.Thread(target=self._hw_refresh, daemon=True).start()
        self.after(2500, self._hw_tick)

    def _hw_refresh(self):
        try:
            text = tools.run("hardware_status", {}, self.ctx)
        except Exception as e:
            text = f"Erreur : {e}"
        if self._alive:
            self.after(0, lambda: self.hw.configure(text=text))

    def destroy(self):
        self._alive = False
        super().destroy()


class MaintenancePanel(ctk.CTkToplevel):
    """Entretien : espace disque, nettoyage de caches sûrs, jeux peu joués à désinstaller."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Entretien du PC — Cronux")
        self.geometry("560x640")
        self.transient(app)
        self.ctx = tools.Context(config.load(), app.confirm)
        self.cache_vars = {}

        ctk.CTkLabel(self, text="🧹 Entretien du PC", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 2))
        self.disk = ctk.CTkLabel(self, text="Analyse en cours…", justify="left")
        self.disk.pack(pady=(0, 6))

        self.body = ctk.CTkScrollableFrame(self)
        self.body.pack(fill="both", expand=True, padx=10, pady=4)
        self.cache_box = ctk.CTkFrame(self.body, fg_color="transparent")
        self.cache_box.pack(fill="x")
        self.games_box = ctk.CTkFrame(self.body, fg_color="transparent")
        self.games_box.pack(fill="x", pady=(10, 0))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=10)
        self.msg = ctk.CTkLabel(bar, text="", text_color="gray")
        self.msg.pack(side="left")
        self.clean_btn = ctk.CTkButton(bar, text="Nettoyer la sélection", command=self._clean)
        self.clean_btn.pack(side="right")

        threading.Thread(target=self._analyze, daemon=True).start()
        self.after(150, self.focus_force)

    def _analyze(self):
        self.after(0, lambda: self.msg.configure(text="Analyse…"))
        try:
            data = maintenance.analyze()
            games_list = maintenance.unused_games(self.ctx)
        except Exception as e:
            self.after(0, lambda: self.msg.configure(text=f"Erreur : {e}", text_color="#b91c1c"))
            return
        self.after(0, self._render, data, games_list)

    def _render(self, data, games_list):
        self.msg.configure(text="")
        lines = []
        for d in data["drives"]:
            pct = d["free"] * 100 // d["total"] if d["total"] else 0
            lines.append(f"Disque {d['drive']}  {maintenance._fmt(d['free'])} libres / "
                         f"{maintenance._fmt(d['total'])}  ({pct} % libre)")
        self.disk.configure(text="\n".join(lines))

        for w in self.cache_box.winfo_children():
            w.destroy()
        total = sum(c["size"] for c in data["caches"])
        ctk.CTkLabel(self.cache_box, text=f"À nettoyer (sûr) — {maintenance._fmt(total)}",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", pady=(0, 4))
        self.cache_vars = {}
        for c in sorted(data["caches"], key=lambda c: -c["size"]):
            if c["size"] <= 0:
                continue
            v = ctk.BooleanVar(value=True)
            self.cache_vars[c["key"]] = v
            ctk.CTkCheckBox(self.cache_box, variable=v,
                            text=f"{c['label']}  —  {maintenance._fmt(c['size'])}").pack(anchor="w", pady=2)

        for w in self.games_box.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.games_box, text="Jeux que tu ne joues plus",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", pady=(4, 2))
        if not games_list:
            ctk.CTkLabel(self.games_box, text="Aucun jeu délaissé repéré. 👍",
                         text_color="gray", anchor="w").pack(fill="x")
        for g in games_list[:12]:
            row = ctk.CTkFrame(self.games_box, fg_color=CARD_COLOR, corner_radius=8)
            row.pack(fill="x", pady=3)
            when = (f"{g['inactive_days']} j sans y jouer" if g["inactive_days"] is not None
                    else "jamais vu lancé")
            ctk.CTkLabel(row, text=f"{g['name']}\n{maintenance._fmt(g['size'])} · {when}",
                         anchor="w", justify="left").pack(side="left", padx=10, pady=6)
            ctk.CTkButton(row, text="Désinstaller", width=100, fg_color="transparent", border_width=1,
                          text_color=("black", "white"),
                          command=lambda g=g: self._uninstall(g)).pack(side="right", padx=8)

    def _clean(self):
        keys = [k for k, v in self.cache_vars.items() if v.get()]
        if not keys:
            self.msg.configure(text="Rien de sélectionné.", text_color="gray")
            return
        if not messagebox.askyesno("Nettoyer", "Supprimer les fichiers temporaires sélectionnés ?\n"
                                   "(sans risque : ils sont recréés automatiquement)", parent=self):
            return
        self.clean_btn.configure(state="disabled", text="Nettoyage…")
        threading.Thread(target=self._do_clean, args=(keys,), daemon=True).start()

    def _do_clean(self, keys):
        freed, _ = maintenance.clean(keys)
        self.after(0, lambda: self.msg.configure(text=f"✓ {maintenance._fmt(freed)} libérés",
                                                 text_color="#15803d"))
        self.after(0, lambda: self.clean_btn.configure(state="normal", text="Nettoyer la sélection"))
        threading.Thread(target=self._analyze, daemon=True).start()

    def _uninstall(self, g):
        if not messagebox.askyesno("Désinstaller", f"Ouvrir la désinstallation de « {g['name']} » ?\n"
                                   f"({maintenance._fmt(g['size'])} seront récupérés)", parent=self):
            return
        try:
            msg = maintenance.uninstall_game(g["root"])
            self.msg.configure(text=msg, text_color="#15803d")
        except Exception as e:
            self.msg.configure(text=f"Erreur : {e}", text_color="#b91c1c")


class DiscordPanel(ctk.CTkToplevel):
    """Connexion Discord : « Se connecter avec Discord » (officiel) + bot pour les messages."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Connexion Discord — Cronux")
        self.geometry("520x560")
        self.transient(app)
        self.cfg = config.load()

        ctk.CTkLabel(self, text="Connexion Discord", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 2))
        self.status = ctk.CTkLabel(self, text="", wraplength=470, justify="center")
        self.status.pack(pady=(0, 8))

        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=12, pady=4)

        step1 = ctk.CTkFrame(body, fg_color=CARD_COLOR, corner_radius=10)
        step1.pack(fill="x", pady=5)
        ctk.CTkLabel(step1, text="1. Ton app Discord (une seule fois)", font=ctk.CTkFont(weight="bold"),
                     anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkButton(step1, text="Comment l'obtenir (ouvrir la page Discord)", height=26,
                      command=self._help).pack(anchor="w", padx=10, pady=4)
        redirect = ctk.CTkFrame(step1, fg_color="transparent")
        redirect.pack(fill="x", padx=10, pady=(2, 0))
        ctk.CTkLabel(redirect, text="Redirect à coller dans Discord (OAuth2) :", anchor="w",
                     text_color="gray").pack(side="left")
        ctk.CTkButton(redirect, text="Copier", width=60, height=24,
                      command=self._copy_redirect).pack(side="right")
        ctk.CTkLabel(step1, text=discord_auth.REDIRECT_URI, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT).pack(fill="x", padx=10)
        self.cid = self._field(step1, "Client ID", self.cfg.get("discord_client_id", ""))
        self.csecret = self._field(step1, "Client Secret", self.cfg.get("discord_client_secret", ""), secret=True)

        step2 = ctk.CTkFrame(body, fg_color=CARD_COLOR, corner_radius=10)
        step2.pack(fill="x", pady=5)
        ctk.CTkLabel(step2, text="2. Connecte ton compte", font=ctk.CTkFont(weight="bold"),
                     anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(step2, text="Ouvre Discord dans le navigateur et te demande d'autoriser Cronux "
                                 "(ton identité et la liste de tes serveurs).",
                     text_color="gray", anchor="w", justify="left", wraplength=460).pack(fill="x", padx=10)
        self.connect_btn = ctk.CTkButton(step2, text="🔗  Se connecter avec Discord",
                                         fg_color="#5865F2", hover_color="#4752C4", command=self._connect)
        self.connect_btn.pack(anchor="w", padx=10, pady=8)

        step3 = ctk.CTkFrame(body, fg_color=CARD_COLOR, corner_radius=10)
        step3.pack(fill="x", pady=5)
        ctk.CTkLabel(step3, text="3. Lire et écrire dans tes serveurs (bot)", font=ctk.CTkFont(weight="bold"),
                     anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(step3, text="Discord n'autorise la lecture/écriture de messages qu'à un bot "
                                 "(un compte perso automatisé est interdit). Colle le token du bot, "
                                 "puis invite-le sur ton serveur en un clic.",
                     text_color="gray", anchor="w", justify="left", wraplength=460).pack(fill="x", padx=10)
        self.token = self._field(step3, "Token du bot", self.cfg.get("discord_bot_token", ""), secret=True)
        ctk.CTkButton(step3, text="➕  Inviter le bot sur un serveur", height=28,
                      command=self._invite).pack(anchor="w", padx=10, pady=8)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=10)
        self.saved = ctk.CTkLabel(bar, text="", text_color="#15803d")
        self.saved.pack(side="left")
        ctk.CTkButton(bar, text="Enregistrer", command=self._save).pack(side="right")
        ctk.CTkButton(bar, text="Se déconnecter", fg_color="transparent", border_width=1,
                      text_color=("black", "white"), command=self._disconnect).pack(side="right", padx=6)

        self._refresh_status()
        self.after(150, self.focus_force)

    def _field(self, parent, label, value, secret=False):
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", padx=10, pady=(4, 0))
        var = ctk.StringVar(value=value or "")
        ctk.CTkEntry(parent, textvariable=var, show="•" if secret else None).pack(fill="x", padx=10, pady=(0, 6))
        return var

    def _help(self):
        url, steps = config.HELP_LINKS["discord"]
        webbrowser.open(url)
        messagebox.showinfo("Comment l'obtenir", steps, parent=self)

    def _copy_redirect(self):
        self.clipboard_clear()
        self.clipboard_append(discord_auth.REDIRECT_URI)
        self.saved.configure(text="Redirect copié ✓")
        self.after(2000, lambda: self.saved.configure(text=""))

    def _refresh_status(self):
        acc = discord_auth.account()
        if acc:
            self.status.configure(text=f"✓ Connecté en tant que {acc.get('username', '')}", text_color="#15803d")
        else:
            self.status.configure(text="Non connecté", text_color="gray")

    def _save(self):
        config.update({"discord_client_id": self.cid.get().strip(),
                       "discord_client_secret": self.csecret.get().strip(),
                       "discord_bot_token": self.token.get().strip()})
        self.cfg = config.load()
        self.saved.configure(text="Enregistré ✓")
        self.after(2000, lambda: self.saved.configure(text=""))

    def _connect(self):
        self._save()
        self.connect_btn.configure(state="disabled", text="Connexion en cours…")
        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        ok, msg = discord_auth.connect(self.cid.get().strip(), self.csecret.get().strip(),
                                       on_status=lambda s: self.status.configure(text=s, text_color="gray"))
        self.status.configure(text=("✓ " if ok else "⚠ ") + msg, text_color="#15803d" if ok else "#b91c1c")
        self.connect_btn.configure(state="normal", text="🔗  Se connecter avec Discord")
        if ok:
            self._refresh_status()

    def _invite(self):
        cid = self.cid.get().strip()
        if not cid:
            messagebox.showwarning("Invitation", "Renseigne d'abord le Client ID.", parent=self)
            return
        webbrowser.open(discord_auth.bot_invite_url(cid))

    def _disconnect(self):
        discord_auth.disconnect()
        self._refresh_status()
        self.saved.configure(text="Déconnecté")
        self.after(2000, lambda: self.saved.configure(text=""))


class Toast(ctk.CTkToplevel):
    """Bulle flottante en bas à droite de l'écran, qui disparaît toute seule."""

    WIDTH = 340
    MARGIN = 16
    GAP = 10

    def __init__(self, app, notif, on_click=None):
        super().__init__(app)
        self.app = app
        self.on_click = on_click
        self._closed = False
        self.overrideredirect(True)            # pas de barre de titre
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.0)     # pour un fondu d'apparition
        except Exception:
            pass

        is_call = notif.get("app", "").lower().find("discord") >= 0 and sounds.is_call(notif)
        accent = ("#DC2626", "#B91C1C") if (is_call or notif.get("important")) else ("#5865F2", "#5865F2")
        card = ctk.CTkFrame(self, corner_radius=12, border_width=2, border_color=accent)
        card.pack(fill="both", expand=True)
        bar = ctk.CTkFrame(card, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(8, 0))
        icon = "📞" if is_call else ("💬" if "discord" in notif.get("app", "").lower() else "🔔")
        ctk.CTkLabel(bar, text=f"{icon}  {notif.get('app', '')}", anchor="w",
                     text_color=accent, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(bar, text="✕", width=22, height=22, fg_color="transparent",
                      text_color=("gray40", "gray70"), hover=False,
                      command=self.close).pack(side="right")
        ctk.CTkLabel(card, text=notif.get("title", ""), anchor="w", justify="left",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     wraplength=self.WIDTH - 28).pack(fill="x", padx=12, pady=(2, 0))
        if notif.get("body"):
            ctk.CTkLabel(card, text=notif["body"][:220], anchor="w", justify="left",
                         wraplength=self.WIDTH - 28).pack(fill="x", padx=12, pady=(0, 8))
        else:
            ctk.CTkLabel(card, text="").pack(pady=(0, 4))

        for w in (self, card):
            w.bind("<Button-1>", self._clicked)
        for child in card.winfo_children():
            child.bind("<Button-1>", self._clicked)

        self.update_idletasks()
        app.register_toast(self)
        self._fade_in()
        # Les appels restent affichés plus longtemps
        self.after(12000 if is_call else 6500, self.close)

    def place_at(self, y_from_bottom):
        h = self.winfo_reqheight()
        x = self.winfo_screenwidth() - self.WIDTH - self.MARGIN
        y = self.winfo_screenheight() - y_from_bottom - h - 60  # 60 : au-dessus de la barre des tâches
        self.geometry(f"{self.WIDTH}x{h}+{x}+{y}")
        return h

    def _fade_in(self, a=0.0):
        if self._closed:
            return
        a = min(0.97, a + 0.15)
        try:
            self.attributes("-alpha", a)
        except Exception:
            pass
        if a < 0.97:
            self.after(20, lambda: self._fade_in(a))

    def _clicked(self, _=None):
        if self.on_click:
            self.on_click()
        self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.app.unregister_toast(self)
        try:
            self.destroy()
        except Exception:
            pass


class SpotifyPanel(ctk.CTkToplevel):
    """Mini-lecteur Spotify : lecture/pause, suivant, précédent, volume, aléatoire, recherche."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Spotify — Cronux")
        self.geometry("360x280")
        self.resizable(False, False)
        self.transient(app)
        self.ctx = tools.Context(config.load(), app.confirm)

        self.now = ctk.CTkLabel(self, text="…", font=ctk.CTkFont(size=14, weight="bold"),
                                wraplength=320, justify="center")
        self.now.pack(pady=(16, 4), padx=12)
        self.sub = ctk.CTkLabel(self, text="", text_color="gray")
        self.sub.pack()

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(pady=10)
        ctk.CTkButton(controls, text="⏮", width=48, command=lambda: self._do("previous")).grid(row=0, column=0, padx=4)
        self.play_btn = ctk.CTkButton(controls, text="⏯", width=64, command=self._toggle)
        self.play_btn.grid(row=0, column=1, padx=4)
        ctk.CTkButton(controls, text="⏭", width=48, command=lambda: self._do("next")).grid(row=0, column=2, padx=4)
        ctk.CTkButton(controls, text="🔀", width=48, command=lambda: self._do("shuffle_on")).grid(row=0, column=3, padx=4)

        vol = ctk.CTkFrame(self, fg_color="transparent")
        vol.pack(fill="x", padx=16)
        ctk.CTkLabel(vol, text="🔉").pack(side="left")
        self.vol = ctk.CTkSlider(vol, from_=0, to=100, command=self._volume)
        self.vol.set(50)
        self.vol.pack(side="left", fill="x", expand=True, padx=6)
        ctk.CTkLabel(vol, text="🔊").pack(side="left")

        search = ctk.CTkFrame(self, fg_color="transparent")
        search.pack(fill="x", padx=16, pady=(10, 8))
        self.q = ctk.CTkEntry(search, placeholder_text="Jouer un titre, un artiste…")
        self.q.pack(side="left", fill="x", expand=True)
        self.q.bind("<Return>", lambda e: self._play_query())
        ctk.CTkButton(search, text="▶", width=40, command=self._play_query).pack(side="left", padx=(6, 0))

        self._alive = True
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._tick()
        self.after(150, self.focus_force)

    def _run(self, fn, *a, then=None):
        def work():
            try:
                res = fn(self.ctx, *a)
            except Exception as e:
                res = f"Erreur : {e}"
            if then and self._alive:
                self.after(0, then, res)
        threading.Thread(target=work, daemon=True).start()

    def _do(self, action):
        self._run(tools.spotify_control, action, then=lambda r: self._refresh_soon())

    def _toggle(self):
        # Lecture/pause intelligent selon l'état courant
        def after(info):
            action = "pause" if info.startswith("En lecture") else "resume"
            self._run(tools.spotify_control, action, then=lambda r: self._refresh_soon())
        self._run(tools.spotify_now_playing, then=after)

    def _volume(self, value):
        self._run(tools.spotify_control, "volume", int(value))

    def _play_query(self):
        q = self.q.get().strip()
        if q:
            self.q.delete(0, "end")
            self.now.configure(text="Lancement…")
            self._run(tools.spotify_play, q, "track", then=lambda r: self._refresh_soon())

    def _refresh_soon(self):
        self.after(600, self._update)

    def _update(self):
        self._run(tools.spotify_now_playing, then=self._show)

    def _show(self, info):
        if info.startswith("Erreur") or "configuré" in info:
            self.now.configure(text="Spotify non connecté")
            self.sub.configure(text="Ajoute ton Client ID dans ⚙ → Spotify")
        elif info.startswith(("En lecture", "En pause")):
            state, _, rest = info.partition(" : ")
            title, _, artist = rest.partition(" — ")
            self.now.configure(text=title or "—")
            self.sub.configure(text=f"{artist}   ·   {state}")
        else:
            self.now.configure(text=info)
            self.sub.configure(text="")

    def _tick(self):
        if not self._alive:
            return
        self._update()
        self.after(4000, self._tick)  # rafraîchit le morceau en cours

    def _close(self):
        self._alive = False
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Cronux")
        self.geometry("460x680")
        self.minsize(380, 480)
        try:
            self.iconbitmap(resource("cronux.ico"))
        except Exception:
            pass
        self.busy = False
        self.labels = []
        self.panel = None
        self.settings_win = None
        self.memory_win = None
        self.spotify_win = None
        self.discord_win = None
        self.maint_win = None
        self.gaming_win = None
        self.overlay = None
        self.toasts = []
        self.agent = Agent(confirm=self.confirm)

        # ── En-tête
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(top, text="Cronux", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(top, text=f"v{VERSION}", text_color="gray",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(6, 0))
        ctk.CTkButton(top, text="⚙", width=34, command=self.open_settings).pack(side="right")
        ctk.CTkButton(top, text="⬆", width=34, command=self.update_app).pack(side="right", padx=4)
        ctk.CTkButton(top, text="🧠", width=34, command=self.open_memory).pack(side="right", padx=4)
        self.bell = ctk.CTkButton(top, text="🔔", width=48, command=self.open_notifs)
        self.bell.pack(side="right")
        ctk.CTkButton(top, text="🎵", width=34, command=self.open_spotify).pack(side="right", padx=4)
        ctk.CTkButton(top, text="🧹", width=34, command=self.open_maintenance).pack(side="right", padx=4)
        ctk.CTkButton(top, text="⚡", width=34, command=self.open_gaming).pack(side="right", padx=4)
        ctk.CTkButton(top, text="Nouveau", width=70, command=self.new_chat).pack(side="right", padx=4)
        self.pin = ctk.CTkSwitch(top, text="📌", width=40, command=self.toggle_pin)
        self.pin.pack(side="right", padx=4)

        # ── Conversation
        self.chat = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.chat.pack(fill="both", expand=True, padx=8, pady=4)
        self.status = ctk.CTkLabel(self, text="", text_color="gray", height=18)
        self.status.pack(fill="x", padx=14)

        # ── Saisie
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=12, pady=(4, 12))
        self.entry = ctk.CTkEntry(bottom, placeholder_text="Demande-moi quelque chose…", height=40)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send())
        self.send_btn = ctk.CTkButton(bottom, text="➤", width=44, height=40, command=self.send)
        self.send_btn.pack(side="left", padx=(6, 0))
        self.entry.focus()
        self.bind("<Configure>", self._on_resize)

        previous = memory.last_conversation()
        if previous:
            for m in previous[-6:]:
                self.add_bubble(m["content"], "user" if m["role"] == "user" else "bot")
        else:
            self.add_bubble("Salut, moi c'est Cronux ! Je peux chercher et ouvrir tes fichiers, lancer des apps, "
                            "gérer Spotify, Outlook et ton agenda, trier tes notifications (Discord compris) "
                            "et t'aider en jeu à trouver un objet. Et j'apprends de toi au fil du temps.", "bot")
        self.update_badge()
        self._record_version()
        try:
            startup.sync(config.load())
        except Exception:
            pass
        threading.Thread(target=self._startup_check, daemon=True).start()
        threading.Thread(target=self._watch_notifications, daemon=True).start()

    # ── Affichage
    def _wrap(self):
        return max(200, self.chat.winfo_width() - 90)

    def add_bubble(self, text, who):
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        row = ctk.CTkFrame(self.chat, fg_color="transparent")
        row.pack(fill="x", pady=4)
        color = {"user": USER_COLOR, "notif": NOTIF_COLOR}.get(who, BOT_COLOR)
        lbl = ctk.CTkLabel(row, text=text, wraplength=self._wrap(), justify="left", anchor="w",
                           fg_color=color, text_color="white" if who == "user" else ("black", "white"),
                           corner_radius=12, padx=12, pady=8)
        lbl.pack(side="right" if who == "user" else "left", padx=6)
        lbl.bind("<Button-3>", lambda e, t=text: self._copy(t))
        if who == "notif":
            lbl.bind("<Button-1>", lambda e: self.open_notifs())
        self.labels.append(lbl)
        self.after(50, lambda: self.chat._parent_canvas.yview_moveto(1.0))

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status("Copié ✓")
        self.after(1500, lambda: self.set_status(""))

    def _on_resize(self, _):
        w = self._wrap()
        for lbl in self.labels:
            lbl.configure(wraplength=w)

    def set_status(self, text):
        self.status.configure(text=text)

    def update_badge(self):
        n = notifications.unseen_important()
        self.bell.configure(text=f"🔔 {n}" if n else "🔔",
                            fg_color=("#DC2626", "#B91C1C") if n else ctk.ThemeManager.theme["CTkButton"]["fg_color"])

    # ── Conversation
    def send(self):
        text = self.entry.get().strip()
        if not text or self.busy:
            return
        self.entry.delete(0, "end")
        self.add_bubble(text, "user")
        self.busy = True
        self.send_btn.configure(state="disabled")
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text):
        try:
            reply = self.agent.ask(text, on_status=lambda s: self.after(0, self.set_status, s))
        except Exception as e:
            reply = f"Oups : {e}"
        self.after(0, self._done, reply)

    def _done(self, reply):
        self.add_bubble(reply, "bot")
        self.set_status("")
        self.busy = False
        self.send_btn.configure(state="normal")
        self.entry.focus()

    def confirm(self, title, message):
        """Appelé depuis un thread : affiche une fenêtre Oui/Non et attend la réponse."""
        done, result = threading.Event(), {}

        def ask():
            result["ok"] = messagebox.askyesno(title, message, parent=self)
            done.set()
        self.after(0, ask)
        done.wait()
        return result["ok"]

    # ── Notifications (surveillance en arrière-plan)
    def _watch_notifications(self):
        """Vérifie toutes les quelques secondes : une notification s'affiche en moins de 15 s."""
        time.sleep(2)
        while True:
            cfg = config.load()
            interval = min(10, max(2, int(cfg.get("notif_check_seconds", 4))))
            if cfg.get("notif_watch", True):
                try:
                    if notifications.db_changed():
                        new, first = notifications.fetch_new()
                        if new:
                            classify_notifications(new, time_budget=max(3, min(7, 13 - interval)))
                            notifications.add(new, seen=first)
                            if not first:
                                self.after(0, self._on_new_notifs, new)
                            else:
                                self.after(0, self.update_badge)
                except Exception:
                    pass
            time.sleep(interval)

    def _on_new_notifs(self, new):
        cfg = config.load()
        if cfg.get("notif_sound", True):
            # Son pour les messages/appels Discord, et pour une notif importante d'une autre app.
            for n in new:
                sounds.play_for(n)
        if cfg.get("notif_bubble", True):
            # Bulle flottante pour les messages Discord et les notifs importantes.
            for n in new:
                if "discord" in n.get("app", "").lower() or n.get("important"):
                    self._show_toast(n)
        for n in [x for x in new if x.get("important")][-3:]:
            body = f"\n{n['body'][:160]}" if n["body"] else ""
            self.add_bubble(f"🔔 {n['app']} · {n['title']}{body}", "notif")
        self.update_badge()
        if self.panel is not None and self.panel.winfo_exists():
            self.panel.refresh()

    # ── Bulles flottantes (empilées en bas à droite)
    def _show_toast(self, notif):
        try:
            Toast(self, notif, on_click=self.open_notifs)
        except Exception:
            pass

    def register_toast(self, toast):
        self.toasts.append(toast)
        self._restack_toasts()

    def unregister_toast(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
        self._restack_toasts()

    def _restack_toasts(self):
        y = 0
        for t in reversed(self.toasts[-5:]):  # au plus 5 bulles à l'écran
            if t.winfo_exists():
                y += t.place_at(y) + Toast.GAP

    def open_notifs(self):
        if self.panel is not None and self.panel.winfo_exists():
            self.panel.refresh()
            self.panel.focus_force()
        else:
            self.panel = NotifPanel(self)

    def open_spotify(self):
        if self.spotify_win is not None and self.spotify_win.winfo_exists():
            self.spotify_win.focus_force()
        else:
            self.spotify_win = SpotifyPanel(self)

    def open_discord(self):
        if self.discord_win is not None and self.discord_win.winfo_exists():
            self.discord_win.focus_force()
        else:
            self.discord_win = DiscordPanel(self)

    def open_maintenance(self):
        if self.maint_win is not None and self.maint_win.winfo_exists():
            self.maint_win.focus_force()
        else:
            self.maint_win = MaintenancePanel(self)

    def open_gaming(self):
        if self.gaming_win is not None and self.gaming_win.winfo_exists():
            self.gaming_win.focus_force()
        else:
            self.gaming_win = GamingPanel(self)

    def toggle_overlay(self):
        if self.overlay is not None and self.overlay.winfo_exists():
            self.overlay.close()
            self.overlay = None
        else:
            self.overlay = Overlay(self)

    # ── Boutons
    def new_chat(self):
        if self.busy:
            return
        self.agent.reset()
        for child in self.chat.winfo_children():
            child.destroy()
        self.labels.clear()
        self.add_bubble("Nouvelle conversation. Je garde en mémoire ce que j'ai appris sur toi.", "bot")

    def update_app(self):
        """Mise à jour en un seul fichier : tu choisis le nouveau Cronux.pyw, il remplace l'actuel."""
        from tkinter import filedialog
        self_path = os.environ.get("CRONUX_SELF")
        if not self_path or not os.path.exists(self_path):
            messagebox.showinfo("Mise à jour",
                                "Pour mettre à jour : enregistre le nouveau Cronux.pyw que je te donne "
                                "par-dessus l'ancien (même dossier, même nom). C'est tout !", parent=self)
            return
        new = filedialog.askopenfilename(title="Choisis le nouveau Cronux.pyw",
                                         filetypes=[("Cronux", "Cronux*.pyw *.pyw")])
        if not new:
            return
        try:
            with open(new, "rb") as f:
                data = f.read()
            if b"CRONUX_BUNDLE" not in data:
                messagebox.showwarning("Mise à jour", "Ce fichier ne ressemble pas à un Cronux.pyw valide.",
                                       parent=self)
                return
            with open(self_path, "wb") as f:   # un .pyw n'est pas verrouillé : on peut l'écraser
                f.write(data)
        except Exception as e:
            messagebox.showerror("Mise à jour", f"Impossible de remplacer le fichier : {e}", parent=self)
            return
        if messagebox.askyesno("Terminé", "Cronux est à jour ✓  Le relancer maintenant ?", parent=self):
            try:
                pyw = sys.executable.replace("python.exe", "pythonw.exe")
                subprocess.Popen([pyw, self_path])
            except Exception:
                pass
            self.after(300, self.destroy)

    def open_settings(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.focus_force()
        else:
            self.settings_win = SettingsPanel(self)

    def open_memory(self):
        if self.memory_win is not None and self.memory_win.winfo_exists():
            self.memory_win.refresh()
            self.memory_win.focus_force()
        else:
            self.memory_win = MemoryPanel(self)

    def toggle_pin(self):
        self.attributes("-topmost", bool(self.pin.get()))

    def _record_version(self):
        try:
            os.makedirs(config.APP_DIR, exist_ok=True)
            with open(os.path.join(config.APP_DIR, "installed_version.txt"), "w", encoding="utf-8") as f:
                f.write(VERSION)
        except Exception:
            pass

    def _startup_check(self):
        problem = check_ollama()
        if problem:
            self.after(0, self.add_bubble, problem, "bot")


if __name__ == "__main__":
    App().mainloop()
