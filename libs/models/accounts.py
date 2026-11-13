"""Modèle : les comptes et leurs sessions (storages/rosalie.sqlite3, ORM SQLAlchemy).

Utilisé par tout Rosalie : le site (connexion, rôles), Discord (à qui elle obéit), les commandes.

Chaque compte peut être lié à son identifiant Discord : sur Discord, Rosalie obéit aux comptes
liés dont le rôle a au moins une permission « act.* » (c'est ce qui remplace l'ancien OWNER_IDS).

Premier lancement : tant qu'aucun compte n'existe, le site demande de créer le superadmin avec
un code d'installation affiché dans la console (sinon le premier venu pourrait le prendre).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path

from sqlalchemy import delete, func, select

from libs.config.schema import SettingError
from libs.db import Database
from libs.models.role import SUPERADMIN
from libs.models.roles import Roles
from libs.models.user import (DISCORD_ID, MIN_PASSWORD, USERNAME, LoginSession, User, check_password,
                              hash_password)

SESSION_DAYS = 30
_DUMMY_HASH = hash_password(secrets.token_hex(8))   # même durée qu'un vrai compte si inconnu


class Accounts:
    def __init__(self, path: Path):
        self.path = path
        self.db = Database(path, "main")
        self.roles = Roles(self.db)
        self.setup_code: str | None = None
        if not self.count():
            code = secrets.token_hex(4).upper()
            self.setup_code = f"{code[:4]}-{code[4:]}"

    def close(self):
        self.db.close()

    # --- lecture ----------------------------------------------------------------------------
    def count(self) -> int:
        with self.db.read() as session:
            return session.scalar(select(func.count()).select_from(User))

    def users(self) -> list[User]:
        with self.db.read() as session:
            return list(session.scalars(select(User).order_by(User.id)))

    def get(self, user_id: int | str) -> User | None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None
        with self.db.read() as session:
            return session.get(User, user_id)

    def find(self, username: str) -> User | None:
        """Par nom, sans tenir compte des majuscules (colonne COLLATE NOCASE)."""
        with self.db.read() as session:
            return session.scalar(select(User).where(User.username == username.strip()))

    def discord_owner_ids(self) -> frozenset[int]:
        """Identifiants Discord pour qui Rosalie agit : comptes liés avec au moins une « act.* »."""
        with self.db.read() as session:
            linked = session.scalars(select(User).where(User.discord_id.is_not(None))).unique()
            return frozenset(int(user.discord_id) for user in linked if user.is_owner)

    def find_by_discord(self, discord_id: int | str) -> User | None:
        with self.db.read() as session:
            return session.scalar(select(User).where(User.discord_id == str(discord_id)))

    # --- écriture ---------------------------------------------------------------------------
    def create(self, username: str, password: str, role: str = "user",
               discord_id: str | None = None) -> User:
        username = username.strip()
        if not USERNAME.match(username):
            raise SettingError("nom d'utilisateur : 2 à 32 caractères (lettres, chiffres, . _ -)")
        self.roles.require(role)
        _check_password(password)
        discord_id = _discord_id(discord_id)
        with self.db.transaction() as session:
            if session.scalar(select(User.id).where(User.username == username)) is not None:
                raise SettingError(f"« {username} » existe déjà")
            _check_discord_free(session, discord_id, None)
            user = User(username=username, password=hash_password(password), role=role,
                        created=time.time(), discord_id=discord_id)
            session.add(user)
        self.setup_code = None
        return self.get(user.id)   # relu : avec son rôle et ses permissions

    def setup(self, code: str, username: str, password: str) -> User:
        """Crée le premier compte (superadmin) avec le code d'installation."""
        if self.count() or not self.setup_code:
            raise SettingError("l'installation est déjà faite")
        if not hmac.compare_digest(code.strip().upper().encode(), self.setup_code.encode()):
            raise SettingError("code d'installation incorrect (il est affiché dans la console)")
        return self.create(username, password, SUPERADMIN)

    def set_role(self, user_id: int, role: str):
        role = self.roles.require(role).name
        with self.db.transaction() as session:
            user = _require(session, user_id)
            if user.role == SUPERADMIN and role != SUPERADMIN:
                _keep_a_superadmin(session)
            user.role = role

    def set_discord(self, user_id: int, discord_id: str | None):
        """Lie (ou délie avec None) un compte à son identifiant Discord."""
        discord_id = _discord_id(discord_id)
        with self.db.transaction() as session:
            user = _require(session, user_id)
            _check_discord_free(session, discord_id, user.id)
            user.discord_id = discord_id

    def set_password(self, user_id: int, password: str, keep_session: str | None = None):
        """Change le mot de passe et ferme les autres sessions de ce compte."""
        _check_password(password)
        with self.db.transaction() as session:
            user = _require(session, user_id)
            user.password = hash_password(password)
            kept = _hash_token(keep_session) if keep_session else ""
            session.execute(delete(LoginSession).where(LoginSession.user_id == user.id,
                                                       LoginSession.token_hash != kept))

    def delete(self, user_id: int):
        with self.db.transaction() as session:
            user = _require(session, user_id)
            if user.role == SUPERADMIN:
                _keep_a_superadmin(session)
            session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
            session.delete(user)

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.find(username)
        if not check_password(password, user.password if user else _DUMMY_HASH) or user is None:
            return None
        with self.db.transaction() as session:
            stored = session.get(User, user.id)
            stored.last_login = time.time()
        return stored

    def verify_password(self, user_id: int, password: str) -> bool:
        user = self.get(user_id)
        return user is not None and check_password(password, user.password)

    # --- sessions ---------------------------------------------------------------------------
    def open_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.db.transaction() as session:
            session.execute(delete(LoginSession).where(LoginSession.expires < now))
            session.add(LoginSession(token_hash=_hash_token(token), user_id=user_id,
                                     expires=now + SESSION_DAYS * 86400))
        return token

    def session_user(self, token: str | None) -> User | None:
        if not token:
            return None
        with self.db.read() as session:
            return session.scalar(select(User).join(LoginSession, LoginSession.user_id == User.id).where(
                LoginSession.token_hash == _hash_token(token), LoginSession.expires > time.time()))

    def close_session(self, token: str | None):
        if token:
            with self.db.transaction() as session:
                session.execute(delete(LoginSession).where(LoginSession.token_hash == _hash_token(token)))


def _require(session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise SettingError("ce compte n'existe pas")
    return user


def _keep_a_superadmin(session):
    count = session.scalar(select(func.count()).select_from(User).where(User.role == SUPERADMIN))
    if count <= 1:
        raise SettingError("il doit rester au moins un superadmin")


def _check_discord_free(session, discord_id: str | None, user_id: int | None):
    if discord_id is None:
        return
    other = session.scalar(select(User).where(User.discord_id == discord_id))
    if other is not None and other.id != user_id:
        raise SettingError(f"cet identifiant Discord est déjà lié au compte « {other.username} »")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _discord_id(value) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    value = str(value).strip()
    if not DISCORD_ID.match(value):
        raise SettingError("identifiant Discord : 15 à 21 chiffres (clic droit sur ton profil > "
                           "Copier l'identifiant, mode développeur requis)")
    return value


def _check_password(password: str):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise SettingError(f"mot de passe : {MIN_PASSWORD} caractères minimum")
