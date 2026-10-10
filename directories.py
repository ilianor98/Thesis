"""Διαδρομές του έργου.

Οι βάσεις δεδομένων βρίσκονται σε έναν φάκελο δεδομένων, ο οποίος επιλέγεται με την εξής σειρά:
  1. μεταβλητή περιβάλλοντος THESIS_DATA_DIR
  2. ρύθμιση "data_dir" στο settings.json (τοπικό αρχείο, ορίζεται και από το UI)
  3. ο φάκελος "vasi" δίπλα στον φάκελο του έργου (../vasi)
"""
import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = PROJECT_DIR / "settings.json"     # δεν ανεβαίνει στο git
EXAMPLE_DIR = PROJECT_DIR / "example"             # βάση αποτελεσμάτων-παράδειγμα (ανεβαίνει στο git)

HARVESTER_NAME = "harvester.db"
RESULTS_NAME = "orismoi.db"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(**values) -> None:
    settings = load_settings()
    settings.update(values)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def data_dir() -> Path:
    env = os.environ.get("THESIS_DATA_DIR")
    if env:
        return Path(env)
    configured = load_settings().get("data_dir")
    if configured:
        return Path(configured)
    return PROJECT_DIR.parent / "vasi"


DATA_DIR = data_dir()
DEFAULT_HARVESTER = DATA_DIR / HARVESTER_NAME
DEFAULT_RESULTS = DATA_DIR / RESULTS_NAME
