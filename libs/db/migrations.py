"""Outils partagés par les env.py d'Alembic (migrations/<base>/env.py) et les migrations."""
from __future__ import annotations

import os
from pathlib import Path

import sqlalchemy as sa


def run(context, metadata, filename: str):
    """Lance les migrations : sur la connexion fournie par l'application (Database), ou, en
    ligne de commande (alembic …), sur la base de STORAGE_DIR (ou -x db=<chemin>)."""
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _migrate(context, connection, metadata)
        return
    from libs.db.database import make_engine
    target = context.get_x_argument(as_dictionary=True).get("db")
    if not target:
        root = Path(__file__).resolve().parent.parent.parent
        storage = Path(os.getenv("STORAGE_DIR") or "storages")
        target = str(storage if storage.is_absolute() else root / storage) + "/" + filename
    engine = make_engine(target)
    with engine.begin() as connection:
        _migrate(context, connection, metadata)
    engine.dispose()


def _migrate(context, connection, metadata):
    context.configure(connection=connection, target_metadata=metadata,
                      render_as_batch=True,    # SQLite : ALTER TABLE limité, Alembic recrée la table
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


# --- pour les migrations ------------------------------------------------------------------------
def has_table(name: str) -> bool:
    from alembic import op
    return name in sa.inspect(op.get_bind()).get_table_names()


def has_column(table: str, column: str) -> bool:
    from alembic import op
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
