"""Magasin des réglages et des personnalités : storages/config.sqlite3 (privé, ignoré par git).

Stockage : ORM SQLAlchemy (libs/models/config.py), schéma tenu par migrations/config/.

Lecture rapide : tout est gardé en mémoire. Toute écriture (de ce processus ou d'un autre :
`python bot.py settings`, `python bot.py web`) est détectée par `PRAGMA data_version`, lu sur
une connexion dédiée — quelques microsecondes : `refresh()` ne recharge que si la base a changé.
`revision` augmente à chaque changement.

Personnalités : des fichiers Markdown.
  - intégrées : personas/*.md du dépôt (lecture seule, `rosalie` par défaut) ;
  - personnalisées : storages/personas/<nom>.md (privées, avec les autres données). Un fichier
    modifié à la main est repris à chaud, comme un réglage (refresh() compare leurs dates).
"""
from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from libs.models.config import Meta, Setting
from libs.config.schema import BY_KEY, FIELDS, PERSONA_NAME, SettingError, find, normalize
from libs.db import Database

DEFAULT_PERSONA = "rosalie"


@dataclass(frozen=True)
class PersonaInfo:
    name: str
    builtin: bool
    size: int


class ConfigStore:
    def __init__(self, path: Path, builtin_personas: Path | None = None,
                 custom_personas: Path | None = None):
        from libs.config import ROOT_DIR
        self.path = path
        self.builtin_dir = builtin_personas or ROOT_DIR / "personas"
        self.custom_dir = custom_personas or path.parent / "personas"   # storages/personas/
        self.db = Database(path, "config")
        self.__lock = threading.RLock()
        # Connexion dédiée à la détection des changements (data_version est propre à chaque
        # connexion : elle voit les écritures de toutes les autres, y compris les nôtres)
        self.__watch = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.__values: dict[str, Any] = {}
        self.__personas: dict[str, str] = {}
        self.__files: tuple = ()   # (nom, date, taille) des fichiers de personnalités
        self.__data_version: int | None = None
        self.revision = 0
        self.refresh()

    def close(self):
        with self.__lock:
            self.__watch.close()
        self.db.close()

    # --- cache --------------------------------------------------------------------------------
    def refresh(self) -> bool:
        """Recharge si la base ou les fichiers de personnalités ont changé. True si c'est le cas."""
        with self.__lock:
            version = self.__watch.execute("PRAGMA data_version").fetchone()[0]
            files = self.__scan()
            if version == self.__data_version and files == self.__files:
                return False
            if version != self.__data_version:
                self.__data_version = version
                with self.db.read() as session:
                    self.__values = {row.key: row.value for row in session.scalars(select(Setting))
                                     if row.key in BY_KEY}   # réglage supprimé du schéma : ignoré
            if files != self.__files:
                self.__files = files
                self.__personas = self.__read_personas()
            self.revision += 1
            return True

    def __scan(self) -> tuple:
        try:
            entries = [(e.name, e.stat().st_mtime_ns, e.stat().st_size) for e in os.scandir(self.custom_dir)
                       if e.name.endswith(".md") and e.is_file()]
        except FileNotFoundError:
            return ()
        return tuple(sorted(entries))

    def __read_personas(self) -> dict[str, str]:
        personas = {}
        for name, _, _ in self.__files:
            stem = name[:-3]
            if stem != stem.lower() or not PERSONA_NAME.match(stem):
                continue   # nom de fichier invalide : ignoré
            try:
                personas[stem] = (self.custom_dir / name).read_text(encoding="utf-8")
            except OSError:
                pass
        return personas

    # --- réglages -----------------------------------------------------------------------------
    def overrides(self) -> dict[str, Any]:
        """Seulement les réglages modifiés (différents de la valeur par défaut)."""
        return dict(self.__values)

    def values(self) -> dict[str, Any]:
        """Tous les réglages : valeur enregistrée, sinon valeur par défaut."""
        stored = self.__values
        return {field.key: stored.get(field.key, field.default) for field in FIELDS}

    def get(self, key: str) -> Any:
        field = find(key)
        return self.__values.get(field.key, field.default)

    def update(self, changes: dict[str, Any]) -> list[str]:
        """Applique plusieurs changements d'un coup (tout ou rien). `None` = valeur par défaut.
        Retourne les clés réellement modifiées."""
        prepared: dict[str, Any] = {}
        for name, value in changes.items():
            field = find(name)
            if value is not None:
                value = normalize(field, value)
                self.__check(field.kind, value)
                if value == field.default:
                    value = None   # pas besoin de stocker la valeur par défaut
            prepared[field.key] = value
        changed = [key for key, value in prepared.items()
                   if self.__values.get(key, BY_KEY[key].default)
                   != (BY_KEY[key].default if value is None else value)]
        with self.db.transaction() as session:
            for key, value in prepared.items():
                if value is None:
                    session.execute(delete(Setting).where(Setting.key == key))
                else:
                    session.merge(Setting(key=key, value=value))
        self.refresh()
        return changed

    def set(self, key: str, value: Any) -> list[str]:
        return self.update({key: value})

    def reset(self, key: str) -> list[str]:
        return self.update({key: None})

    def take_legacy(self, key: str):
        """Lit puis retire un réglage qui n'existe plus dans le schéma (migration)."""
        with self.db.transaction() as session:
            row = session.get(Setting, key)
            if row is None:
                return None
            value = row.value
            session.delete(row)
        self.refresh()
        return value

    def __check(self, kind: str, value: Any):
        if kind == "persona" and self.persona_text(value) is None:
            raise SettingError(f"la personnalité « {value} » n'existe pas")
        if kind == "tools":
            from libs.config.schema import tool_catalog
            known = {tool["name"] for tool in tool_catalog()}
            unknown = [name for name in value if name not in known]
            if unknown:
                raise SettingError(f"outil inconnu : {', '.join(unknown)}")

    # --- personnalités ------------------------------------------------------------------------
    def builtin_personas(self) -> dict[str, Path]:
        if not self.builtin_dir.is_dir():
            return {}
        return {path.stem.lower(): path for path in sorted(self.builtin_dir.glob("*.md"))}

    def personas(self) -> list[PersonaInfo]:
        builtin = self.builtin_personas()
        infos = [PersonaInfo(name, True, path.stat().st_size) for name, path in builtin.items()]
        infos += [PersonaInfo(name, False, len(text.encode()))
                  for name, text in sorted(self.__personas.items()) if name not in builtin]
        return infos

    def is_builtin(self, name: str) -> bool:
        return name.lower() in self.builtin_personas()

    def persona_text(self, name: str) -> str | None:
        """Texte d'une personnalité (None si elle n'existe pas). Les intégrées sont relues
        sur le disque à chaque appel : `Persona` garde le résultat en cache."""
        path = self.builtin_personas().get(name.lower())
        if path is not None:
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return None
        return self.__personas.get(name.lower())

    def save_persona(self, name: str, text: str, *, create: bool | None = None):
        """create=True : doit être nouvelle ; False : doit exister ; None : peu importe."""
        name = self.__persona_name(name)
        exists = name in self.__personas
        if create is True and exists:
            raise SettingError(f"la personnalité « {name} » existe déjà")
        if create is False and not exists:
            raise SettingError(f"la personnalité « {name} » n'existe pas")
        if not text.strip():
            raise SettingError("le texte de la personnalité est vide")
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        target = self.custom_dir / f"{name}.md"
        temporary = target.with_suffix(".md.tmp")   # écriture atomique : jamais de fichier à moitié écrit
        temporary.write_text(text.strip() + "\n", encoding="utf-8")
        os.replace(temporary, target)
        self.refresh()

    def rename_persona(self, old: str, new: str):
        old = old.lower()
        if self.is_builtin(old):
            raise SettingError(f"« {old} » est intégrée : duplique-la plutôt")
        if old not in self.__personas:
            raise SettingError(f"la personnalité « {old} » n'existe pas")
        new = self.__persona_name(new)
        if new in self.__personas:
            raise SettingError(f"la personnalité « {new} » existe déjà")
        os.replace(self.custom_dir / f"{old}.md", self.custom_dir / f"{new}.md")
        if self.__values.get("persona") == old:
            with self.db.transaction() as session:
                session.merge(Setting(key="persona", value=new))
        self.refresh()

    def delete_persona(self, name: str):
        """Supprime une personnalité ; si c'était l'active, on revient à celle par défaut."""
        name = name.lower()
        if self.is_builtin(name):
            raise SettingError(f"« {name} » est intégrée et ne peut pas être supprimée")
        if name not in self.__personas:
            raise SettingError(f"la personnalité « {name} » n'existe pas")
        (self.custom_dir / f"{name}.md").unlink(missing_ok=True)
        if self.__values.get("persona") == name:
            with self.db.transaction() as session:
                session.execute(delete(Setting).where(Setting.key == "persona"))
        self.refresh()

    def __persona_name(self, name: str) -> str:
        name = name.strip().lower()
        if not PERSONA_NAME.match(name):
            raise SettingError("nom invalide : lettres minuscules, chiffres, - et _ (40 max)")
        if self.is_builtin(name):
            raise SettingError(f"« {name} » est une personnalité intégrée (non modifiable) : "
                               "choisis un autre nom")
        return name

    # --- méta ---------------------------------------------------------------------------------
    def meta(self, key: str) -> str | None:
        with self.db.read() as session:
            row = session.get(Meta, key)
            return row.value if row else None

    def set_meta(self, key: str, value: str):
        with self.db.transaction() as session:
            session.merge(Meta(key=key, value=value))
