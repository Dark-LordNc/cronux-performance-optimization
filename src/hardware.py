"""Surveillance matérielle : CPU, RAM, disque, et GPU NVIDIA (via nvidia-smi)."""
import os
import shutil
import subprocess
import sys
import threading
import time

from tools import tool

IS_WIN = sys.platform == "win32"
GB = 1024 ** 3
GPU_TEMP_ALERT = 83  # °C : seuil d'alerte


_SMI = {"path": False}                      # False = pas encore cherché
_GPU_CACHE = {"time": 0.0, "data": []}
_GPU_LOCK = threading.Lock()
GPU_CACHE_SECONDS = 1.5  # l'overlay et le panneau Gaming interrogent le GPU en même temps


def _nvidia_smi():
    if _SMI["path"] is False:
        path = shutil.which("nvidia-smi")
        if not path and IS_WIN:
            candidate = r"C:\Windows\System32\nvidia-smi.exe"
            path = candidate if os.path.exists(candidate) else None
        _SMI["path"] = path
    return _SMI["path"]


def gpu_status():
    """Renvoie une liste de GPU NVIDIA (ou [] si pas de carte/nvidia-smi).
    Résultat gardé ~1,5 s : lancer nvidia-smi coûte cher et plusieurs écrans le demandent."""
    with _GPU_LOCK:
        if time.monotonic() - _GPU_CACHE["time"] < GPU_CACHE_SECONDS:
            return [dict(g) for g in _GPU_CACHE["data"]]
        data = _query_gpus()
        _GPU_CACHE.update(time=time.monotonic(), data=data)
        return [dict(g) for g in data]


def _query_gpus():
    exe = _nvidia_smi()
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6,
            creationflags=0x08000000 if IS_WIN else 0)  # pas de fenêtre console
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                name, temp, util, mem_u, mem_t = parts[:5]
                power = parts[5] if len(parts) > 5 else None
                gpus.append({"name": name, "temp": _num(temp), "util": _num(util),
                             "mem_used": _num(mem_u), "mem_total": _num(mem_t),
                             "power": _num(power) if power else None})
        return gpus
    except Exception:
        return []


def _num(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def cpu_temp():
    """Température CPU si disponible (souvent indisponible sous Windows sans pilote dédié)."""
    try:
        import psutil
        temps = getattr(psutil, "sensors_temperatures", lambda: {})()
        for key in ("coretemp", "k10temp", "acpitz", "cpu_thermal"):
            if key in temps and temps[key]:
                return temps[key][0].current
        for entries in temps.values():
            if entries:
                return entries[0].current
    except Exception:
        pass
    return None


def snapshot():
    """Photo instantanée du matériel pour l'affichage en direct."""
    import psutil
    vm = psutil.virtual_memory()
    data = {
        "cpu": psutil.cpu_percent(interval=0.3),
        "cpu_temp": cpu_temp(),
        "ram_percent": vm.percent,
        "ram_used": vm.used,
        "ram_total": vm.total,
        "gpus": gpu_status(),
    }
    return data


@tool("hardware_status", "Donne l'état du matériel : processeur, mémoire, et carte graphique (température, "
                         "charge). Prévient si le GPU chauffe trop.",
      label="Je regarde le matériel")
def hardware_status(ctx):
    if not IS_WIN:
        return "Surveillance disponible sous Windows."
    return format_snapshot(snapshot())


def _fmt0(value, unit):
    """« 42 % » ; « ? % » si la valeur est indisponible (nvidia-smi peut renvoyer « [N/A] »)."""
    return f"{value:.0f} {unit}" if value is not None else f"? {unit}"


def format_snapshot(d):
    lines = [f"Processeur : {d['cpu']:.0f} %" + (f" · {d['cpu_temp']:.0f} °C" if d['cpu_temp'] else "")]
    lines.append(f"Mémoire : {d['ram_percent']:.0f} % ({d['ram_used'] / GB:.1f} / {d['ram_total'] / GB:.1f} Go)")
    if d["gpus"]:
        for g in d["gpus"]:
            seg = f"GPU {g['name']} : {_fmt0(g['util'], '%')} · {_fmt0(g['temp'], '°C')}"
            if g["mem_total"] and g["mem_used"] is not None:
                seg += f" · VRAM {g['mem_used'] / 1024:.1f}/{g['mem_total'] / 1024:.1f} Go"
            if g["power"]:
                seg += f" · {g['power']:.0f} W"
            lines.append(seg)
            if g["temp"] and g["temp"] >= GPU_TEMP_ALERT:
                lines.append(f"⚠ Attention : le GPU est à {g['temp']:.0f} °C, c'est chaud. "
                             "Vérifie la ventilation ou baisse les graphismes.")
    else:
        lines.append("GPU : pas de carte NVIDIA détectée (ou nvidia-smi indisponible).")
    return "\n".join(lines)
