"""Interface Discord : traduit les messages Discord pour le cœur de Rosalie, et ses réponses
en messages Discord. Ses outils propres sont dans tools/, ses commandes (/rosalie, ⭐…) dans cogs/.
"""
from __future__ import annotations

import io
import os
from typing import Any

import discord

from interfaces.discord.confirm import ask_code_confirmation, ask_confirmation
from interfaces.discord.utils import message_text, place_name
from libs.core.interface import Interface
from libs.core.types import Conversation, Incoming, OutgoingFile, Person, Sent, make_key
from libs.log import Log

COGS = ("events", "admin", "training", "reload")


class DiscordInterface(Interface):
    name = "discord"
    label = "Discord"
    message_limit = 2000

    def __init__(self, rosalie):
        super().__init__(rosalie)
        import interfaces.discord.tools  # noqa: F401  (enregistre les outils Discord)

        intents = discord.Intents.default()
        intents.message_content = True  # Developer Portal : « Message Content Intent »
        intents.members = True          # Developer Portal : « Server Members Intent »
        self.client = discord.Bot(intents=intents)
        self.client.rosalie = rosalie        # accès au cœur depuis les cogs
        self.client.interface = self
        for cog in COGS:
            self.client.load_extension(f"interfaces.discord.cogs.{cog}")

        @self.client.event
        async def on_ready():
            Log.info(f"Discord : connectée en tant que {self.client.user} ({self.client.user.id})")

    # --- cycle de vie -------------------------------------------------------------------
    async def start(self):
        token = os.getenv("ROSALIE_TOKEN")
        if not token:
            raise RuntimeError("ROSALIE_TOKEN n'est pas défini dans le .env")
        if not self.rosalie.config.owner_ids:
            raise RuntimeError("OWNER_IDS est vide : Rosalie n'obéit qu'aux owners")
        await self.client.start(token)

    async def stop(self):
        if not self.client.is_closed():
            await self.client.close()

    @property
    def bot_name(self) -> str:
        user = self.client.user
        return user.display_name if user else super().bot_name

    def prompt_context(self) -> list[str]:
        guilds = [guild.name for guild in self.client.guilds]
        return [f"Serveurs Discord où tu es présente : {', '.join(guilds)}."] if guilds else []

    # --- Discord -> cœur ------------------------------------------------------------------
    def person_from(self, user: discord.abc.User) -> Person:
        return Person("discord", user.id, user.name, user.display_name,
                      is_owner=user.id in self.rosalie.config.owner_ids, native=user)

    def conversation_from(self, channel, other: discord.abc.User | None = None) -> Conversation:
        private = isinstance(channel, discord.DMChannel)
        place = place_name(channel)
        recipient = getattr(channel, "recipient", None) or other
        if private and recipient is not None:
            place += f" avec {recipient.name}"
        return Conversation("discord", channel.id, place, private=private, native=channel)

    async def incoming_from(self, message: discord.Message) -> Incoming:
        me = self.client.user
        replied = await self.__replied_author(message)
        return Incoming(
            conversation=self.conversation_from(message.channel, message.author),
            author=self.person_from(message.author),
            text=message_text(message, me),
            message_id=message.id,
            has_attachments=bool(message.attachments),
            mentioned=me in message.mentions,
            reply_to_bot=None if replied is None else replied == me.id,
            mentions_other=any(user.id != me.id for user in message.mentions),
            native=message,
        )

    async def __replied_author(self, message: discord.Message) -> int | None:
        reference = message.reference
        if reference is None or reference.message_id is None:
            return None
        if isinstance(reference.resolved, discord.Message):
            return reference.resolved.author.id
        try:
            return (await message.channel.fetch_message(reference.message_id)).author.id
        except discord.HTTPException:
            return None

    # --- cœur -> Discord ------------------------------------------------------------------
    async def send(self, conversation: Conversation, text: str | None = None, *,
                   files: list[OutgoingFile] = (), reply_to: Any = None) -> Sent:
        channel = conversation.native
        kwargs: dict = {"files": [discord.File(io.BytesIO(f.data), filename=f.filename) for f in files]}
        if reply_to is not None and not conversation.private:
            kwargs["reference"] = discord.MessageReference(
                message_id=int(reply_to), channel_id=channel.id, fail_if_not_exists=False)
            kwargs["mention_author"] = False
        message = await channel.send(text or None, **kwargs)
        return Sent(message.id, conversation, message)

    def typing(self, conversation: Conversation):
        return conversation.native.typing()

    async def react(self, conversation: Conversation, message_id: Any, emoji: str):
        try:
            await conversation.native.get_partial_message(int(message_id)).add_reaction(emoji)
        except (discord.HTTPException, AttributeError, ValueError):
            pass

    async def confirm(self, conversation: Conversation, text: str, *, code: str | None = None,
                      language: str | None = None) -> tuple[bool, Sent | None]:
        owners = self.rosalie.config.owner_ids
        if code is None:
            return await ask_confirmation(conversation.native, owners, text), None
        confirmed, shown = await ask_code_confirmation(conversation.native, owners, language, code)
        return confirmed, Sent(shown.id, conversation, shown)

    # --- retrouver ------------------------------------------------------------------------
    async def conversation(self, conversation_id: str) -> Conversation | None:
        try:
            channel_id = int(conversation_id)
            channel = self.client.get_channel(channel_id) or await self.client.fetch_channel(channel_id)
        except (ValueError, discord.HTTPException):
            return None
        return self.conversation_from(channel)

    async def person(self, person_id: str) -> Person | None:
        try:
            user_id = int(person_id)
            user = self.client.get_user(user_id) or await self.client.fetch_user(user_id)
        except (ValueError, discord.HTTPException):
            return None
        return self.person_from(user)

    async def destination(self, query: str, current: Conversation | None) -> Conversation:
        from interfaces.discord.tools.helpers import find_channel
        native = current.native if current is not None and current.interface == self.name else None
        return self.conversation_from(await find_channel(self.client, query, native))

    def describe_error(self, error: Exception) -> str | None:
        if isinstance(error, discord.Forbidden):
            return "Erreur : je n'ai pas la permission Discord pour faire ça."
        if isinstance(error, discord.HTTPException):
            return f"Erreur Discord : {error.text or error}"
        return None


def make_conversation_key(channel_id: int) -> str:
    return make_key("discord", channel_id)
