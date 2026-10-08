"""Démarrage automatique de Cronux avec Windows (clé de registre HKCU\\...\\Run)."""
import os
import sys

APP_NAME = "Cronux"


def _target_command():
    """Commande à lancer au démarrage, selon qu'on tourne en .exe ou via Cronux.bat/python."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    here = os.path.dirname(os.path.abspath(__file__))
    bat = os.path.join(here, "Cronux.bat")
    if os.path.exists(bat):
        return f'"{bat}"'
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{pyw}" "{os.path.join(here, "main.py")}"'


def _key():
    import winreg
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                          r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                          winreg.KEY_READ | winreg.KEY_WRITE)


def is_enabled():
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with _key() as k:
            winreg.QueryValueEx(k, APP_NAME)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_enabled(enabled):
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with _key() as k:
            if enabled:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _target_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def sync(cfg):
    """Aligne le registre sur le réglage start_with_windows."""
    want = bool(cfg.get("start_with_windows", False))
    if want != is_enabled():
        set_enabled(want)
