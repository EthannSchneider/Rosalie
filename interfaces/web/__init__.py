"""Interface web : le site de Rosalie (panneau de réglages + chat), servi par libs/webui.

Chaque compte (libs/models/) a sa conversation privée avec elle : clé « web:<id> ».
Un compte dont le rôle a la permission « act » est son créateur (outils, souvenirs, code
confirmé) ; sans elle, il discute seulement, comme un invité sur Discord.

Le site lui-même (API MVC /api/v1, React) est dans libs/webui ; cette interface fait le lien
avec le cœur. Le serveur HTTP tourne dans des fils ; tout ce qui touche au cœur repasse par la
boucle asyncio de Rosalie (`run_coroutine_threadsafe` / `call_soon_threadsafe`). Les messages
partent vers les navigateurs en Server-Sent Events (EventHub).
"""
from __future__ import annotations

import asyncio
from typing import Any

from libs.config import WebUIOptions
from libs.config.schema import SettingError
from libs.core.interface import Interface
from libs.core.types import Conversation, Incoming, OutgoingFile, Person, Sent, make_key
from libs.log import Log
from libs.webui.events import EventHub
from libs.models import main_database
from libs.models.chat import ChatFile, ChatLog, ChatMessage
from libs.models.user import User
from libs.webui.server import WebServer
from libs.webui.views.chat import message_event, typing_event, update_event

CONFIRM_TIMEOUT = 300   # secondes
MAX_MESSAGE = 20_000


class WebInterface(Interface):
    name = "web"
    label = "le chat web"   # « tu parles via le chat web (en tête-à-tête avec …) »
    message_limit = 100_000

    def __init__(self, rosalie, options: WebUIOptions | None = None):
        super().__init__(rosalie)
        storage = rosalie.config.storage_dir
        options = options or WebUIOptions.from_env()
        self.log = ChatLog(main_database(storage), storage / "web_files")
        self.hub = EventHub()
        self.server = WebServer(rosalie.store, options.host, options.port,
                                storage=storage, chat=self, accounts=rosalie.accounts)
        self.accounts = rosalie.accounts
        self.loop: asyncio.AbstractEventLoop | None = None
        self.__stopped = asyncio.Event()
        self.__pending: dict[int, tuple[asyncio.Future, str]] = {}   # confirmations
        self.__typing: dict[str, int] = {}

    # --- cycle de vie -------------------------------------------------------------------
    async def start(self):
        self.loop = asyncio.get_running_loop()
        self.server.start()
        Log.info(f"Site web (réglages + chat) : {self.server.url}")
        self.server.announce_setup()
        try:
            await self.__stopped.wait()
        finally:
            self.server.stop()
            self.log.close()

    async def stop(self):
        self.__stopped.set()

    # --- comptes -> cœur ----------------------------------------------------------------
    def person_of(self, user: User) -> Person:
        return Person(self.name, user.id, user.username, user.username, is_owner=user.is_owner,
                      native=user)

    def conversation_of(self, user: User) -> Conversation:
        return Conversation(self.name, user.id, f"en tête-à-tête avec {user.username}",
                            private=True, native=user)

    @staticmethod
    def key_of(user: User) -> str:
        return make_key("web", user.id)

    # --- appelé par le serveur HTTP (autres fils) ---------------------------------------
    def history(self, user: User, before: int | None = None) -> list[ChatMessage]:
        return self.log.history(self.key_of(user), before)

    def post(self, user: User, text: str) -> ChatMessage:
        text = text.strip()
        if not text:
            raise SettingError("message vide")
        if len(text) > MAX_MESSAGE:
            raise SettingError(f"message trop long ({MAX_MESSAGE} caractères max)")
        loop = self.__loop()
        message = self.log.add(self.key_of(user), "user", text)
        self.hub.publish(user.id, message_event(message))
        incoming = Incoming(self.conversation_of(user), self.person_of(user), text,
                            message_id=message.id)
        asyncio.run_coroutine_threadsafe(self.rosalie.receive(incoming), loop)
        return message

    def user_typing(self, user: User):
        """La personne écrit : Rosalie attend un peu avant de répondre."""
        self.__loop().call_soon_threadsafe(self.rosalie.typing_from, self.key_of(user),
                                           self.person_of(user).key)

    def answer(self, user: User, message_id: int, accept: bool):
        pending = self.__pending.get(message_id)
        if pending is None or pending[1] != self.key_of(user):
            raise SettingError("cette demande n'attend plus de réponse")
        if not user.is_owner:
            raise SettingError("il faut la permission « Faire agir Rosalie » pour confirmer")
        future = pending[0]
        self.__loop().call_soon_threadsafe(lambda: future.done() or future.set_result(accept))

    def reset(self, user: User):
        """Efface la conversation (affichage + mémoire courte de Rosalie ; souvenirs gardés)."""
        key = self.key_of(user)
        self.log.clear(key)

        def clear():
            self.rosalie.memory.clear(key)
            self.rosalie.decider.stop(key)
        self.__loop().call_soon_threadsafe(clear)

    def file(self, user: User, file_id: str) -> ChatFile | None:
        return self.log.file(self.key_of(user), file_id)

    def __loop(self) -> asyncio.AbstractEventLoop:
        if self.loop is None or self.loop.is_closed():
            raise SettingError("Rosalie n'est pas prête")
        return self.loop

    # --- cœur -> navigateur ---------------------------------------------------------------
    async def send(self, conversation: Conversation, text: str | None = None, *,
                   files: list[OutgoingFile] = (), reply_to: Any = None) -> Sent:
        saved = [self.log.save_file(conversation.key, f.filename, f.data) for f in files]
        meta = {"files": saved} if saved else {}
        if reply_to is not None:
            meta["reply_to"] = reply_to
        message = self.log.add(conversation.key, "rosalie", text or "", meta=meta)
        self.hub.publish(int(conversation.id), message_event(message))
        return Sent(message.id, conversation)

    def typing(self, conversation: Conversation):
        return _Typing(self, conversation)

    def _set_typing(self, conversation: Conversation, delta: int):
        count = self.__typing.get(conversation.key, 0) + delta
        self.__typing[conversation.key] = max(0, count)
        if count in (0, 1):
            self.hub.publish(int(conversation.id), typing_event(count > 0))

    async def react(self, conversation: Conversation, message_id: Any, emoji: str):
        try:
            message = self.log.get(int(message_id))
        except (TypeError, ValueError):
            return
        if message is None or message.conversation != conversation.key:
            return
        reactions = list(dict.fromkeys([*message.meta.get("reactions", []), emoji]))
        updated = self.log.update_meta(message.id, reactions=reactions)
        self.hub.publish(int(conversation.id), update_event(updated))

    async def confirm(self, conversation: Conversation, text: str, *, code: str | None = None,
                      language: str | None = None) -> tuple[bool, Sent | None]:
        meta = {"status": "pending"}
        if code is not None:
            meta |= {"code": code, "language": language or ""}
        message = self.log.add(conversation.key, "rosalie", text, kind="confirm", meta=meta)
        user_id = int(conversation.id)
        future = asyncio.get_running_loop().create_future()
        self.__pending[message.id] = (future, conversation.key)
        self.hub.publish(user_id, message_event(message))
        try:
            confirmed = await asyncio.wait_for(future, timeout=CONFIRM_TIMEOUT)
            status = "accepted" if confirmed else "refused"
        except asyncio.TimeoutError:
            confirmed, status = False, "expired"
        finally:
            self.__pending.pop(message.id, None)
        updated = self.log.update_meta(message.id, status=status)
        self.hub.publish(user_id, update_event(updated))
        return confirmed, Sent(message.id, conversation)

    # --- retrouver ------------------------------------------------------------------------
    async def conversation(self, conversation_id: str) -> Conversation | None:
        user = self.accounts.get(conversation_id)
        return self.conversation_of(user) if user else None

    async def person(self, person_id: str) -> Person | None:
        user = self.accounts.get(person_id)
        return self.person_of(user) if user else None


class _Typing:
    def __init__(self, interface: WebInterface, conversation: Conversation):
        self.__interface = interface
        self.__conversation = conversation

    async def __aenter__(self):
        self.__interface._set_typing(self.__conversation, +1)

    async def __aexit__(self, *exc):
        self.__interface._set_typing(self.__conversation, -1)
        return False
