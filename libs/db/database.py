from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def make_engine(path: Path | str) -> Engine:
    """Moteur SQLite partagé entre les fils (WAL : lectures pendant les écritures)."""
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def _pragmas(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class Database:
    def __init__(self, path: Path, migrations: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.engine = make_engine(path)
        upgrade(self.engine, migrations)
        self.__sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextlib.contextmanager
    def transaction(self) -> Iterator[Session]:
        """Une session : commit à la sortie, rollback si exception. Les objets restent lisibles
        après (expire_on_commit=False)."""
        with self.__sessions.begin() as session:
            yield session

    def read(self) -> Session:
        """Session de lecture (à utiliser avec `with`)."""
        return self.__sessions()

    def close(self):
        self.engine.dispose()


def upgrade(engine: Engine, migrations: str):
    """Applique les migrations manquantes (alembic upgrade head) sur cette base."""
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR / migrations))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
