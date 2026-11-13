"""Types échangés entre le serveur et les contrôleurs : la requête, les réponses, les erreurs.

Un contrôleur reçoit une `Request` et renvoie une `Json`, un `Stream` (Server-Sent Events) ou un
`File` ; il signale un refus en levant `HttpError` (ou `SettingError`, traduite en 400).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from libs.models.user import User


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Request:
    method: str
    path: str
    params: dict[str, str] = field(default_factory=dict)   # morceaux du chemin : /users/{id}
    query: dict[str, str] = field(default_factory=dict)
    body: Any = None
    user: User | None = None
    token: str | None = None                                # jeton de session (cookie)
    client: str = ""                                        # adresse IP

    def text(self, key: str) -> str:
        """Champ texte obligatoire du corps JSON."""
        value = self.body.get(key) if isinstance(self.body, dict) else None
        if not isinstance(value, str):
            raise HttpError(400, f"« {key} » attendu")
        return value

    def optional(self, key: str, default: Any = None) -> Any:
        return self.body.get(key, default) if isinstance(self.body, dict) else default

    def has(self, key: str) -> bool:
        return isinstance(self.body, dict) and key in self.body

    def int_param(self, key: str) -> int:
        try:
            return int(self.params[key])
        except (KeyError, ValueError):
            raise HttpError(404, "introuvable") from None


@dataclass
class Json:
    data: Any
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Stream:
    """Flux Server-Sent Events : `events` produit des morceaux de texte déjà formatés ; `close`
    est appelé quand le navigateur se déconnecte."""
    events: Iterator[str]
    close: Callable[[], None] = lambda: None


@dataclass
class File:
    path: Path
    name: str
    content_type: str
    inline: bool = False
