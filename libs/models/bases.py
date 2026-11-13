"""Les deux bases SQLite de Rosalie et leur base ORM (une par fichier, une par dossier de migrations).

  ConfigBase   storages/config.sqlite3    réglages            migrations/config/
  MainBase     storages/rosalie.sqlite3   comptes, sessions,  migrations/main/
                                          historique du chat
"""
from sqlalchemy.orm import DeclarativeBase


class ConfigBase(DeclarativeBase):
    pass


class MainBase(DeclarativeBase):
    pass
