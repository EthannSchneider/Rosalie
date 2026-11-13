"""Bases de données de Rosalie : SQLite via l'ORM SQLAlchemy, schéma tenu par des migrations
Alembic (dossier migrations/).

    db = Database(storage / "rosalie.sqlite3", "main")   # crée/met à jour le schéma (migrations)
    with db.transaction() as session:                 # commit à la fin, rollback si erreur
        session.add(User(...))

Changer un modèle = une nouvelle migration (voir docs/developpement.md) :
    alembic -c migrations/alembic.ini --name main revision --autogenerate -m "ce qui change"
"""
from libs.db.database import Database

__all__ = ["Database"]
