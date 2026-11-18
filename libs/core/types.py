"""Ce que le cœur de Rosalie sait d'une messagerie, sans dépendre d'aucune.

Chaque interface (Discord, terminal…) traduit ses objets natifs en ces types.
Une clé « interface:id » identifie une personne ou une conversation partout
(mémoire, agenda, relances).
"""
import base64
from dataclasses import dataclass, field
from typing import Any


def to_data_uri(data: bytes, content_type: str = "image/png") -> str:
    """Bytes d'une image -> data URI base64 (la forme interne : les fournisseurs distants et
    Ollama (qui veut du base64 brut) en tirent le format qu'ils attendent, voir libs/llm/)."""
    mime = (content_type or "").split(";")[0].strip().lower() or "image/png"
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def make_key(interface: str, native_id) -> str:
    return f"{interface}:{native_id}"


def split_key(key: str) -> tuple[str, str]:
    interface, _, native_id = str(key).partition(":")
    return interface, native_id


@dataclass
class Person:
    interface: str
    id: Any                    # id natif (int pour Discord, « local » pour le terminal…)
    name: str                  # identifiant (pseudo)
    display_name: str          # nom affiché
    is_owner: bool = False     # elle peut agir pour lui (au moins une permission « act.* »)
    native: Any = None         # objet de l'interface (discord.User…)
    # Ce qu'elle peut faire pour lui (libs/models/role.py : web, act.memory, act.code…).
    # None = tout si is_owner (terminal : c'est ta machine), sinon invité : recherche web seulement.
    permissions: frozenset[str] | None = None

    @property
    def key(self) -> str:
        return make_key(self.interface, self.id)

    def can(self, permission: str) -> bool:
        if self.permissions is None:
            return self.is_owner or permission == "web"
        return permission in self.permissions

    def __str__(self) -> str:
        return self.name


@dataclass
class Conversation:
    interface: str
    id: Any
    place: str                 # description lisible : « en message privé », « salon #général… »
    private: bool = False      # tête-à-tête (DM, terminal) : elle répond toujours
    native: Any = None         # objet de l'interface (salon Discord…)

    @property
    def key(self) -> str:
        return make_key(self.interface, self.id)


@dataclass
class Incoming:
    """Un message reçu, avec les signaux que l'interface sait calculer."""
    conversation: Conversation
    author: Person
    text: str
    message_id: Any = None
    # Images du message, en data URIs base64 (elles sont montrées au modèle ; la mémoire
    # n'en garde que le nom de fichier)
    images: tuple[str, ...] = field(default_factory=tuple)
    has_attachments: bool = False
    mentioned: bool = False            # @mention de Rosalie
    reply_to_bot: bool | None = None   # réponse à un message : à elle (True), à quelqu'un d'autre (False)
    mentions_other: bool = False       # mentionne quelqu'un d'autre
    native: Any = None


@dataclass
class Sent:
    """Référence d'un message envoyé par Rosalie (pour y répondre, le retrouver…)."""
    id: Any = None
    conversation: Conversation | None = None
    native: Any = None


@dataclass
class OutgoingFile:
    filename: str
    data: bytes = field(repr=False)
