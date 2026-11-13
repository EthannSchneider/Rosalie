"""Vues JSON : comptes et session."""
from __future__ import annotations

from libs.models.user import User


def user_json(user: User) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role,
            "created": user.created, "last_login": user.last_login, "discord_id": user.discord_id,
            # ce que le compte peut faire (l'interface adapte ses pages)
            "owner": user.is_owner, "settings": user.can_edit_settings, "users": user.can_manage_users}


def users_json(users: list[User]) -> dict:
    return {"users": [user_json(user) for user in users]}


def session_json(*, name: str, setup: bool, user: User | None, chat: bool,
                 legacy_owners: list[str] | None = None) -> dict:
    data = {"name": name, "setup": setup, "user": user_json(user) if user else None, "chat": chat}
    if legacy_owners is not None:
        data["legacy_owners"] = legacy_owners
    return data
