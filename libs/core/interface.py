"""Contrat d'une interface : tout ce dont le cœur de Rosalie a besoin d'une messagerie.

Ajouter une interface (Telegram, WhatsApp, web…) = une sous-classe d'Interface dans
interfaces/<nom>/, enregistrée dans interfaces/__init__.py. Elle :
  - transforme les messages reçus en `Incoming` et appelle `self.rosalie.receive(incoming)`
    (et `self.rosalie.typing_from(...)` si la messagerie signale « écrit… ») ;
  - sait envoyer, montrer « écrit… », demander une confirmation, retrouver une
    conversation/personne par id (pour le heartbeat et les relances).
Ses outils spécifiques (ex : modération Discord) s'enregistrent avec @tool(requires="<nom>").
"""
from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from libs.core.types import Conversation, OutgoingFile, Person, Sent

if TYPE_CHECKING:
    from libs.core.rosalie import Rosalie


class Interface(ABC):
    name: str = ""             # identifiant court, préfixe des clés (« discord »)
    label: str = ""            # nom affiché dans le prompt (« Discord »)
    message_limit: int = 2000  # longueur max d'un message (découpé au-delà)

    def __init__(self, rosalie: Rosalie):
        self.rosalie = rosalie

    # --- cycle de vie ----------------------------------------------------------------
    @abstractmethod
    async def start(self):
        """Démarre l'interface (bloquant tant qu'elle tourne)."""

    async def stop(self):
        pass

    # --- identité -----------------------------------------------------------------------
    @property
    def bot_name(self) -> str:
        return self.rosalie.config.names[0].capitalize() if self.rosalie.config.names else "Rosalie"

    def prompt_context(self) -> list[str]:
        """Lignes ajoutées au prompt système (ex : serveurs Discord où elle est)."""
        return []

    # --- envoyer ------------------------------------------------------------------------
    @abstractmethod
    async def send(self, conversation: Conversation, text: str | None = None, *,
                   files: list[OutgoingFile] = (), reply_to: Any = None) -> Sent:
        """Envoie un message (déjà découpé à message_limit par le cœur). reply_to : id natif."""

    def typing(self, conversation: Conversation):
        """Contexte async affichant « écrit… » pendant qu'elle réfléchit."""
        return contextlib.nullcontext()

    async def react(self, conversation: Conversation, message_id: Any, emoji: str):
        """Réaction à un message (si la messagerie le permet)."""

    @abstractmethod
    async def confirm(self, conversation: Conversation, text: str, *, code: str | None = None,
                      language: str | None = None) -> tuple[bool, Sent | None]:
        """Demande à l'owner de confirmer une action (ou l'exécution de `code`).
        Retourne (confirmé ?, message de la demande pour y répondre)."""

    # --- retrouver (heartbeat, relances, outils) ----------------------------------------
    @abstractmethod
    async def conversation(self, conversation_id: str) -> Conversation | None:
        """Conversation à partir de son id (tel que dans sa clé)."""

    @abstractmethod
    async def person(self, person_id: str) -> Person | None:
        """Personne à partir de son id (tel que dans sa clé)."""

    async def destination(self, query: str, current: Conversation | None) -> Conversation:
        """Conversation désignée par du texte (« #général », « ici »…), pour les outils
        qui envoient ailleurs. Par défaut : seulement la conversation courante."""
        if current is not None and current.interface == self.name:
            return current
        from libs.assistant.tools.base import ToolError
        raise ToolError(f"je ne sais pas envoyer vers « {query} » avec {self.label}")

    def describe_error(self, error: Exception) -> str | None:
        """Traduit une exception propre à la messagerie en message d'erreur lisible."""
        return None
