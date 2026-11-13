"""Modèle : un compte, et ses sessions de connexion.

Ce qu'un compte peut faire dépend des permissions de son rôle (libs/models/role.py) :
`user.has("act.code")`, `user.has("settings")`… Jamais de test sur le nom du rôle.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.models.bases import MainBase
from libs.models.role import PERMISSIONS, SUPERADMIN, Role, acts

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
    role: Mapped[str] = mapped_column(Text, nullable=False)              # roles.name
    created: Mapped[float] = mapped_column(Float, nullable=False)
    last_login: Mapped[float | None] = mapped_column(Float)
    discord_id: Mapped[str | None] = mapped_column(Text, index=True, unique=True)   # son compte Discord

    # Chargé avec le compte (jointure) : utilisable après la fermeture de la session
    role_info: Mapped[Role | None] = relationship(
        Role, primaryjoin="foreign(User.role) == Role.name", lazy="joined", viewonly=True)

    def __repr__(self) -> str:
        return f"User(id={self.id}, username={self.username!r}, role={self.role!r})"

    @property
    def permissions(self) -> frozenset[str]:
        if self.role == SUPERADMIN:
            return frozenset(PERMISSIONS)
        return self.role_info.granted if self.role_info else frozenset()

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def is_superadmin(self) -> bool:
        return self.role == SUPERADMIN

    @property
    def is_owner(self) -> bool:
        """« Owner » de Rosalie : elle agit pour lui (au moins une permission « act.* »)."""
        return acts(self.permissions)


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
