"""Modèles de données de Rosalie (ORM SQLAlchemy), utilisables par n'importe quelle partie :
le cœur (owners Discord), les interfaces (Discord, web, terminal), les commandes, le site.

  config.py    Setting, Meta                      -> storages/config.sqlite3
  role.py      Role, PERMISSIONS                  -> storages/rosalie.sqlite3
  user.py      User, LoginSession
  roles.py     Roles : les rôles et leurs permissions
  accounts.py  Accounts : comptes et sessions (accounts.roles : les rôles)
  chat.py      ChatMessage, ChatFile, ChatLog : historique du chat

Le schéma des bases est tenu par les migrations Alembic (migrations/), appliquées à
l'ouverture (libs/db). Les personnalités personnalisées sont des fichiers (libs/config/store.py).
"""
from __future__ import annotations

from pathlib import Path

from libs.models.accounts import Accounts
from libs.models.bases import ConfigBase, MainBase
from libs.models.chat import ChatFile, ChatLog, ChatMessage
from libs.models.config import Meta, Setting
from libs.models.role import PERMISSIONS, SUPERADMIN, Role
from libs.models.roles import Roles
from libs.models.user import LoginSession, User

MAIN_DATABASE = "rosalie.sqlite3"
_OLD_NAME = "web.sqlite3"   # nom avant que les comptes servent aussi à Discord


def main_database(storage: Path) -> Path:
    """Chemin de storages/rosalie.sqlite3 (renomme l'ancien web.sqlite3 s'il existe encore)."""
    path = storage / MAIN_DATABASE
    old = storage / _OLD_NAME
    if old.exists() and not path.exists():
        for suffix in ("", "-wal", "-shm"):
            source = storage / f"{_OLD_NAME}{suffix}"
            if source.exists():
                source.rename(storage / f"{MAIN_DATABASE}{suffix}")
    return path


__all__ = ["Accounts", "ChatFile", "ChatLog", "ChatMessage", "ConfigBase", "LoginSession", "MAIN_DATABASE",
           "MainBase", "Meta", "PERMISSIONS", "Role", "Roles", "SUPERADMIN", "Setting", "User", "main_database"]
