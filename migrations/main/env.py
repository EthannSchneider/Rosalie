"""Environnement Alembic de storages/rosalie.sqlite3 (comptes, sessions, chat)."""
from alembic import context

from libs.db.migrations import run
from libs.models import MainBase as Base

import libs.models  # noqa: F401,E402  (enregistre toutes les tables)

run(context, Base.metadata, "rosalie.sqlite3")
