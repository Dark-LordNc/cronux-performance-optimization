"""Surveillance matérielle : CPU, RAM, disque, et GPU NVIDIA (via nvidia-smi)."""
import shutil
import subprocess
import sys

from tools import tool

IS_WIN = sys.platform == "win32"
GB = 1024 ** 3
GPU_TEMP_ALERT = 83  # °C : seuil d'alerte


def _nvidia_smi():
    return shutil.which("nvidia-smi") or (
        r"C:\Windows\System32\nvidia-smi.exe" if IS_WIN else None)


def gpu_status():
    """Renvoie une liste de GPU NVIDIA (ou [] si pas de carte/nvidia-smi)."""
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
    d = snapshot()
    lines = [f"Processeur : {d['cpu']:.0f} %" + (f" · {d['cpu_temp']:.0f} °C" if d['cpu_temp'] else "")]
    lines.append(f"Mémoire : {d['ram_percent']:.0f} % ({d['ram_used'] / GB:.1f} / {d['ram_total'] / GB:.1f} Go)")
    if d["gpus"]:
        for g in d["gpus"]:
            seg = f"GPU {g['name']} : {g['util']:.0f} % · {g['temp']:.0f} °C"
            if g["mem_total"]:
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
