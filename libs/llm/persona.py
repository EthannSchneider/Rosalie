from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from libs.log import Log

if TYPE_CHECKING:
    from libs.config.store import ConfigStore


DEFAULT_PERSONA = "Tu es Rosalie, l'assistante personnelle de ton créateur sur Discord."
DEFAULT_NAME = "rosalie"


class Persona:
    """Le prompt système du personnage : la personnalité active des réglages.

    Les personnalités intégrées sont les fichiers personas/*.md (lecture seule) ; les autres
    sont dans storages/config.sqlite3. Le texte est gardé en cache tant que ni le nom actif
    ni les réglages ne changent (`reload()` relit le fichier intégré).
    """

    def __init__(self, name: Callable[[], str] | str, store: ConfigStore):
        self.__name = name if callable(name) else (lambda: name)
        self.__store = store
        self.__cached: tuple | None = None
        self.__text = DEFAULT_PERSONA

    @property
    def name(self) -> str:
        return self.__name()

    @property
    def text(self) -> str:
        key = (self.name, self.__store.revision)
        if key != self.__cached:
            self.__cached = key
            self.__text = self.__load(key[0])
        return self.__text

    def reload(self) -> str:
        self.__cached = None
        return self.text

    def __load(self, name: str) -> str:
        text = self.__store.persona_text(name)
        if text is None and name != DEFAULT_NAME:
            Log.warning(f"Personnalité « {name} » introuvable, retour à « {DEFAULT_NAME} »")
            text = self.__store.persona_text(DEFAULT_NAME)
        if text is None:
            Log.warning("Aucune personnalité trouvée (personas/rosalie.md), texte par défaut")
        return (text or "").strip() or DEFAULT_PERSONA
