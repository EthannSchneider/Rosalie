"""Dépôt : les rôles (table roles de storages/rosalie.sqlite3)."""
from __future__ import annotations

import time

from sqlalchemy import func, select

from libs.config.schema import SettingError
from libs.db import Database
from libs.models.role import PERMISSIONS, ROLE_NAME, SUPERADMIN, Role
from libs.models.user import User


class Roles:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> list[Role]:
        """Superadmin d'abord, puis par date de création."""
        with self.db.read() as session:
            roles = list(session.scalars(select(Role).order_by(Role.created, Role.name)))
        return sorted(roles, key=lambda role: role.name != SUPERADMIN)

    def get(self, name: str) -> Role | None:
        with self.db.read() as session:
            return session.get(Role, name.strip().lower())

    def require(self, name: str) -> Role:
        role = self.get(name) if isinstance(name, str) else None
        if role is None:
            raise SettingError(f"rôle inconnu « {name} » ({', '.join(r.name for r in self.all())})")
        return role

    def counts(self) -> dict[str, int]:
        """Nombre de comptes par rôle."""
        with self.db.read() as session:
            return dict(session.execute(select(User.role, func.count()).group_by(User.role)).all())

    def create(self, name: str, label: str, permissions: list[str], description: str = "") -> Role:
        name = name.strip().lower()
        if not ROLE_NAME.match(name):
            raise SettingError("nom de rôle : 2 à 32 caractères (minuscules, chiffres, - et _)")
        role = Role(name=name, label=_label(label), description=description.strip(),
                    permissions=_permissions(permissions), locked=False, created=time.time())
        with self.db.transaction() as session:
            if session.get(Role, name) is not None:
                raise SettingError(f"le rôle « {name} » existe déjà")
            session.add(role)
        return role

    def update(self, name: str, *, label: str | None = None, description: str | None = None,
               permissions: list[str] | None = None) -> Role:
        with self.db.transaction() as session:
            role = session.get(Role, name)
            if role is None:
                raise SettingError(f"rôle inconnu « {name} »")
            if role.locked:
                raise SettingError(f"« {role.label} » est verrouillé : il a toujours toutes les permissions")
            if label is not None:
                role.label = _label(label)
            if description is not None:
                role.description = description.strip()
            if permissions is not None:
                role.permissions = _permissions(permissions)
        return role

    def delete(self, name: str):
        with self.db.transaction() as session:
            role = session.get(Role, name)
            if role is None:
                raise SettingError(f"rôle inconnu « {name} »")
            if role.locked:
                raise SettingError(f"« {role.label} » est verrouillé et ne peut pas être supprimé")
            used = session.scalar(select(func.count()).select_from(User).where(User.role == name))
            if used:
                raise SettingError(f"{used} utilisateur(s) ont le rôle « {role.label} » : "
                                   "change-leur de rôle d'abord")
            session.delete(role)


def _label(label: str) -> str:
    label = (label or "").strip()
    if not label or len(label) > 40:
        raise SettingError("libellé du rôle : 1 à 40 caractères")
    return label


def _permissions(permissions) -> list[str]:
    if not isinstance(permissions, (list, tuple)):
        raise SettingError("liste de permissions attendue")
    unknown = [p for p in permissions if p not in PERMISSIONS]
    if unknown:
        raise SettingError(f"permission inconnue : {', '.join(map(str, unknown))} ({', '.join(PERMISSIONS)})")
    return [p for p in PERMISSIONS if p in permissions]   # ordre canonique, sans doublon
