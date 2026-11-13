"""Environnement Alembic de storages/config.sqlite3."""
from alembic import context

from libs.db.migrations import run
from libs.models import ConfigBase as Base

import libs.models  # noqa: F401,E402  (enregistre toutes les tables)

run(context, Base.metadata, "config.sqlite3")
