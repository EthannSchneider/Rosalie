"""Modèle : les rôles et leurs permissions.

Les PERMISSIONS sont fixées dans le code (c'est lui qui les vérifie) ; les RÔLES sont des
données (table roles), gérés par qui a la permission « roles ». Le code ne teste jamais un nom
de rôle, seulement des permissions — sauf `superadmin`, verrouillé, qui a toujours tout.
"""
from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy import JSON, Boolean, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.models.bases import MainBase

SUPERADMIN = "superadmin"
ROLE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")

# nom -> (libellé, description). L'ordre est celui de l'affichage.
PERMISSIONS: dict[str, tuple[str, str]] = {
    "chat": ("Chat", "Discuter avec Rosalie sur le site."),
    "act": ("Faire agir Rosalie",
            "Outils, souvenirs, exécution de code (avec confirmation), sur le site et sur Discord "
            "si son identifiant Discord est lié. Sans elle : discussion et recherche seulement."),
    "personas": ("Personnalités", "Créer, modifier et choisir les personnalités."),
    "settings": ("Réglages", "Modifier tous les réglages de Rosalie (token Discord, modèle, outils…)."),
    "users": ("Utilisateurs", "Créer, modifier, supprimer les comptes et choisir leur rôle."),
    "roles": ("Rôles", "Créer et modifier les rôles et leurs permissions."),
}

# Rôles créés au départ (migration main 0003). superadmin est verrouillé ; les autres se modifient.
DEFAULT_ROLES: list[dict[str, Any]] = [
    {"name": SUPERADMIN, "label": "Superadmin", "locked": True, "permissions": list(PERMISSIONS),
     "description": "Tout, y compris les rôles et les utilisateurs. Il en reste toujours au moins un."},
    {"name": "admin", "label": "Admin", "locked": False, "permissions": ["chat", "act"],
     "description": "Rosalie agit pour lui (outils, souvenirs, code), sur le chat web et sur Discord."},
    {"name": "user", "label": "Utilisateur", "locked": False, "permissions": ["chat"],
     "description": "Discute avec Rosalie, comme un invité : discussion et recherche seulement."},
]


class Role(MainBase):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(Text, primary_key=True)          # identifiant (users.role)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)   # superadmin
    created: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)

    def __repr__(self) -> str:
        return f"Role({self.name!r}, {self.permissions})"

    @property
    def granted(self) -> frozenset[str]:
        """Permissions effectives (superadmin : toutes, même celles ajoutées plus tard)."""
        if self.name == SUPERADMIN:
            return frozenset(PERMISSIONS)
        return frozenset(p for p in self.permissions if p in PERMISSIONS)
