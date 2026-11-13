"""Modèle : un compte du site, et ses sessions de connexion.

Rôles :
  superadmin  tout : réglages de Rosalie, personnalités, comptes (il en reste toujours au moins un)
  admin       la fait agir (outils, souvenirs, code), sur le chat web et sur Discord
  user        discute seulement, comme un invité (discussion et recherche, aucune action)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.models.bases import MainBase

ROLES = ("superadmin", "admin", "user")
OWNER_ROLES = ("superadmin", "admin")       # font agir Rosalie (= « owner » sur Discord)
SETTINGS_ROLES = ("superadmin",)            # réglages de Rosalie (globaux)
MIN_PASSWORD = 8
USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,31}$")
DISCORD_ID = re.compile(r"^\d{15,21}$")
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


class User(MainBase):
    __tablename__ = "users"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(collation="NOCASE"), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)          # hash scrypt, jamais affiché
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created: Mapped[float] = mapped_column(Float, nullable=False)
    last_login: Mapped[float | None] = mapped_column(Float)
    discord_id: Mapped[str | None] = mapped_column(Text, index=True, unique=True)   # son compte Discord

    def __repr__(self) -> str:
        return f"User(id={self.id}, username={self.username!r}, role={self.role!r})"

    @property
    def is_owner(self) -> bool:
        return self.role in OWNER_ROLES

    @property
    def can_edit_settings(self) -> bool:
        return self.role in SETTINGS_ROLES

    @property
    def can_manage_users(self) -> bool:
        return self.role == "superadmin"


class LoginSession(MainBase):
    """Une connexion ouverte (cookie). Seul le hash du jeton est stocké."""
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires: Mapped[float] = mapped_column(Float, nullable=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt$" + "$".join(base64.b64encode(part).decode() for part in (salt, digest))


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), dklen=32, **_SCRYPT)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
