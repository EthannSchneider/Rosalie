"""Modèles ORM de storages/config.sqlite3 (schéma tenu par migrations/config/).

Les personnalités ne sont pas en base : ce sont des fichiers (voir libs/config/store.py)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from libs.models.bases import ConfigBase


class Setting(ConfigBase):
    """Un réglage modifié (absent = valeur par défaut du schéma, libs/config/schema.py)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)


class Meta(ConfigBase):
    """Petites informations internes (import du .env fait, anciens OWNER_IDS…)."""
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
