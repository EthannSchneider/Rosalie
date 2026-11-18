"""Vues JSON : comptes, rôles, permissions et session."""
from __future__ import annotations

from libs.models.role import PERMISSIONS, Role
from libs.models.user import User


def user_json(user: User) -> dict:
    role = user.role_info
    return {"id": user.id, "username": user.username, "role": user.role,
            "role_label": role.label if role else user.role,
            "role_description": role.description if role else "",
            "permissions": [p for p in PERMISSIONS if user.has(p)],   # l'interface adapte ses pages
            "superadmin": user.is_superadmin,
            "created": user.created, "last_login": user.last_login, "discord_id": user.discord_id}


def users_json(users: list[User]) -> dict:
    return {"users": [user_json(user) for user in users]}


def role_json(role: Role, users: int = 0) -> dict:
    return {"name": role.name, "label": role.label, "description": role.description,
            "permissions": sorted(role.granted, key=list(PERMISSIONS).index),
            "locked": role.locked, "users": users}


def roles_json(roles: list[Role], counts: dict[str, int]) -> dict:
    return {"roles": [role_json(role, counts.get(role.name, 0)) for role in roles],
            "permissions": [{"name": name, "label": label, "description": description, "group": group}
                            for name, (label, description, group) in PERMISSIONS.items()]}


def session_json(*, name: str, setup: bool, user: User | None, chat: bool,
                 legacy_owners: list[str] | None = None) -> dict:
    data = {"name": name, "setup": setup, "user": user_json(user) if user else None, "chat": chat}
    if legacy_owners is not None:
        data["legacy_owners"] = legacy_owners
    return data
