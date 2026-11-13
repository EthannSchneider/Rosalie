"""Garde-fous contre l'élévation de droits, communs aux utilisateurs et aux rôles :
  - on ne donne un rôle (ou une permission à un rôle) que si on a soi-même ces permissions ;
  - seul un superadmin nomme, modifie ou retire un superadmin.
"""
from __future__ import annotations

from libs.models.role import PERMISSIONS, SUPERADMIN, Role
from libs.models.user import User
from libs.webui.http import HttpError


def can_grant(actor: User, permissions) -> None:
    missing = [p for p in permissions if not actor.has(p)]
    if missing:
        names = ", ".join(PERMISSIONS[p][0] for p in missing if p in PERMISSIONS)
        raise HttpError(403, f"tu ne peux pas donner des permissions que tu n'as pas ({names})")


def can_assign(actor: User, role: Role) -> None:
    if role.name == SUPERADMIN and not actor.is_superadmin:
        raise HttpError(403, "seul un superadmin peut nommer un superadmin")
    can_grant(actor, role.granted)


def can_manage(actor: User, target: User) -> None:
    if target.is_superadmin and not actor.is_superadmin:
        raise HttpError(403, "seul un superadmin peut modifier un superadmin")
