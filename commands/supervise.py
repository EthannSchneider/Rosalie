import os
from pathlib import Path

from libs.supervisor import Supervisor

ROOT_DIR = Path(__file__).resolve().parent.parent


def run():
    """python bot.py supervise — lance Rosalie sous supervision : relancée si elle tombe, et
    mise à jour / redémarrée à la demande d'un superadmin (Évolution du code, docs/evolution.md).
    Volontairement sans le reste du code de Rosalie : une mise à jour ne doit pas pouvoir casser
    le superviseur."""
    storage = Path(os.getenv("STORAGE_DIR") or "storages")
    storage = storage if storage.is_absolute() else ROOT_DIR / storage
    raise SystemExit(Supervisor(ROOT_DIR, storage).run())
