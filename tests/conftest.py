"""Configuration commune des tests : APPDATA isolé dans un dossier temporaire, caches remis à zéro."""
import os
import shutil
import sys
import tempfile

import pytest

_APPDATA = tempfile.mkdtemp(prefix="cronux_test_appdata_")
os.environ["APPDATA"] = _APPDATA
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import config  # noqa: E402
import memory  # noqa: E402
import notifications  # noqa: E402
import tools  # noqa: E402


@pytest.fixture(autouse=True)
def clean_appdata():
    """Chaque test démarre avec un dossier Cronux vide et des caches vides."""
    shutil.rmtree(config.APP_DIR, ignore_errors=True)
    os.makedirs(config.APP_DIR, exist_ok=True)
    config._CACHE.update(stamp=None, cfg=None)
    memory._CACHE.update(stamp=None, data=None)
    notifications._CACHE.update(stamp=None, data=None)
    tools._MAIL_CACHE.clear()
    tools._MAIL_IDS.clear()
    tools._SHORTCUTS.update(time=0.0, items=[])
    yield


@pytest.fixture
def ctx():
    return tools.Context(config.load(), confirm=lambda title, message: True)
