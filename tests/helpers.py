"""Faux objets partagés par les tests : interface factice, Rosalie allégée, contextes d'outils."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import interfaces.discord.tools  # noqa: F401  (enregistre les outils Discord)
from interfaces.discord import DiscordInterface
from libs.assistant.tools import ToolContext
from libs.config import Config
from libs.conversation.agenda import Agenda
from libs.conversation.memory import ConversationMemory
from libs.core.interface import Interface
from libs.core.rosalie import Rosalie
from libs.core.types import Conversation, Person, Sent

OWNER = 42


def make_config(**overrides) -> Config:
    with mock.patch.dict("os.environ", {}, clear=True):
        config = Config.from_env()
    values = {**config.__dict__, "use_llm_decider": False,
              "web_access": True, **overrides}
    return Config(**values)


class FakeInterface(Interface):
    """Interface en mémoire : garde ce qui est envoyé, confirme selon `confirm_answer`."""
    name = "test"
    label = "Test"

    def __init__(self, rosalie, name: str | None = None):
        super().__init__(rosalie)
        if name:
            self.name = name
        self.sent: list[tuple] = []
        self.confirms: list[str] = []
        self.reactions: list[tuple] = []
        self.confirm_answer = True

    async def start(self):
        pass

    async def send(self, conversation, text=None, *, files=(), reply_to=None):
        self.sent.append((conversation.key, text, list(files), reply_to))
        return Sent(len(self.sent), conversation)

    async def confirm(self, conversation, text, *, code=None, language=None):
        self.confirms.append(text if code is None else code)
        return self.confirm_answer, Sent(0, conversation)

    async def react(self, conversation, message_id, emoji):
        self.reactions.append((message_id, emoji))

    async def conversation(self, conversation_id):
        return Conversation(self.name, conversation_id, "test")

    async def person(self, person_id):
        return Person(self.name, person_id, "p", "P", is_owner=True)


class FakeDiscord(FakeInterface):
    """Interface Discord dont le client est un faux bot ; traduit les erreurs comme la vraie."""
    name = "discord"
    label = "Discord"
    describe_error = DiscordInterface.describe_error
    conversation_from = DiscordInterface.conversation_from
    destination = DiscordInterface.destination

    def __init__(self, rosalie, client=None):
        super().__init__(rosalie)
        self.client = client


class FakeRosalie:
    """Les services de Rosalie dont les outils ont besoin, sans LLM ni Discord."""
    send = Rosalie.send
    remember_sent = Rosalie.remember_sent
    interface_of = Rosalie.interface_of
    where = Rosalie.where
    name = "Rosalie"

    def __init__(self, config=None, directory: Path | None = None):
        directory = directory or Path(tempfile.mkdtemp())
        self.config = config or make_config()
        self.memory = ConversationMemory(directory / "memory")
        self.agenda = Agenda(directory / "agenda.json")
        self.long_term = None
        self.browser = None
        self.interfaces: dict[str, Interface] = {}

    def discord_owners(self) -> frozenset[int]:
        return frozenset({OWNER})

    def add(self, interface: Interface) -> Interface:
        self.interfaces[interface.name] = interface
        return interface


def make_ctx(rosalie: FakeRosalie | None = None, *, interface: str = "test", native=None,
             conversation_id=5, person_id=OWNER, owner: bool | None = None,
             private: bool = False) -> ToolContext:
    rosalie = rosalie or FakeRosalie()
    if interface not in rosalie.interfaces:
        rosalie.add(FakeDiscord(rosalie) if interface == "discord" else FakeInterface(rosalie, interface))
    is_owner = person_id in rosalie.discord_owners() if owner is None else owner
    conversation = Conversation(interface, getattr(native, "id", conversation_id), "ici", private, native)
    person = Person(interface, person_id, f"u{person_id}", f"User{person_id}", is_owner)
    return ToolContext(rosalie=rosalie, conversation=conversation, person=person)


def discord_ctx(client, channel=None, author_id: int = OWNER, config=None) -> ToolContext:
    """Contexte pour un outil Discord. channel=None : la demande vient d'une autre interface."""
    rosalie = FakeRosalie(config)
    rosalie.add(FakeDiscord(rosalie, client))
    if channel is None:
        return make_ctx(rosalie, interface="test", person_id=author_id)
    return make_ctx(rosalie, interface="discord", native=channel, person_id=author_id)


def fake_discord_user(id=1, name="Rosalie"):
    return SimpleNamespace(id=id, name=name, display_name=name)
