import asyncio
import contextlib
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass

import discord

from libs.assistant.agent import run_agent
from libs.assistant.code_runner import (REFUSED_NOTE, environment_line, extract_code,
                                        result_note, run_code)
from libs.assistant.confirm import ask_code_confirmation
from libs.assistant.tools import ToolContext
from libs.conversation.initiative import is_silence, with_note
from libs.conversation.memory import Entry
from libs.conversation.prompt import build_messages, build_system_prompt, clean_reply
from libs.llm.ollama import OllamaError
from libs.log import Log
from libs.memory.extractor import extract_memories
from libs.utils.discord_utils import message_text, place_name, split_message


TYPING_EXTEND = 8.0   # un événement « écrit… » dure ~10 s côté Discord


@dataclass
class _Pending:
    """Réponse en attente : elle laisse la personne finir d'écrire avant de répondre."""
    message: discord.Message
    deadline: float
    limit: float
    task: asyncio.Task | None = None


class Chat(discord.Cog):
    """Écoute les messages, attend que tu aies fini d'écrire, fait agir Rosalie et répond
    (ou choisit de se taire). `speak` sert aussi au heartbeat pour qu'elle parle d'elle-même."""

    def __init__(self, bot: discord.Bot):
        self.__bot = bot
        self.__locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.__pending: dict[int, _Pending] = {}
        self.__background: set[asyncio.Task] = set()

    def cog_unload(self):
        for pending in self.__pending.values():
            if pending.task:
                pending.task.cancel()

    # --- écoute -------------------------------------------------------------------
    @discord.Cog.listener()
    async def on_message(self, message: discord.Message):
        bot = self.__bot
        if message.author.bot:
            return

        channel_id = message.channel.id
        Log.message(message.channel, message_text(message, bot.user), message.author.name,
                    bot.user.name)
        history = bot.memory.get(channel_id)
        decision = await bot.decider.decide(message, bot.user, history)

        if decision.record:
            bot.memory.add(channel_id, Entry(
                author_id=message.author.id,
                author_name=message.author.display_name,
                content=message_text(message, bot.user),
                is_bot=False,
                message_id=message.id,
            ))
            if bot.decider.is_owner(message.author.id):
                bot.agenda.set_home(channel_id, message.author.id)
        if not decision:
            Log.info(f"Not replying to {message.author.name} ({decision.reason})")
            return

        Log.info(f"Will reply to {message.author.name} ({decision.reason})")
        self.__schedule(message)

    @discord.Cog.listener()
    async def on_typing(self, channel, user, when):
        """Tu es en train d'écrire la suite : elle attend encore un peu."""
        pending = self.__pending.get(channel.id)
        if pending and user.id == pending.message.author.id:
            pending.deadline = min(pending.limit, time.monotonic() + TYPING_EXTEND)

    def __schedule(self, message: discord.Message):
        config = self.__bot.config
        now = time.monotonic()
        pending = self.__pending.get(message.channel.id)
        if pending:   # elle attendait déjà : on répondra à l'ensemble, après ce message
            pending.message = message
            pending.deadline = min(pending.limit, now + config.reply_delay)
            return
        pending = _Pending(message, now + config.reply_delay, now + config.reply_max_wait)
        self.__pending[message.channel.id] = pending
        pending.task = asyncio.create_task(self.__wait_then_reply(pending))

    async def __wait_then_reply(self, pending: _Pending):
        channel_id = pending.message.channel.id
        try:
            while (remaining := pending.deadline - time.monotonic()) > 0:
                await asyncio.sleep(remaining)
        finally:
            self.__pending.pop(channel_id, None)
        await self.__reply(pending.message)

    async def __reply(self, message: discord.Message):
        bot = self.__bot
        try:
            reply = await self.speak(message.channel, message.author, reply_to=message,
                                     query=message.content)
        except OllamaError as error:
            Log.error(f"Ollama error: {error}")
            await message.reply("Je n'arrive pas à joindre mon cerveau… Ollama est lancé ?",
                                mention_author=False)
            return
        except Exception as error:
            Log.error(f"{error}\n{traceback.format_exc()}")
            await message.reply(f"Oups, j'ai planté : `{error}`", mention_author=False)
            return
        bot.decider.mark_active(message.channel.id, message.author.id)

        if reply is None or not bot.decider.is_owner(message.author.id):
            return   # on ne prend des notes que sur les owners
        # Prise de notes automatique, sans bloquer la conversation
        task = asyncio.create_task(extract_memories(
            bot.llm, bot.config.decider_model, bot.long_term,
            message.author.display_name, message_text(message, bot.user), reply))
        self.__background.add(task)
        task.add_done_callback(self.__background.discard)

    # --- parler -------------------------------------------------------------------
    async def speak(self, channel: discord.abc.Messageable, author: discord.abc.User, *,
                    reply_to: discord.Message | None = None, note: str | None = None,
                    query: str | None = None, spontaneous: bool = False) -> str | None:
        """Fait réfléchir/agir Rosalie dans ce salon et envoie sa réponse.
        Retourne le texte envoyé, ou None si elle a choisi le silence.
        `note` : consigne système ajoutée en fin de conversation (relance, réflexion)."""
        bot = self.__bot
        async with self.__locks[channel.id]:
            # Initiative : pas de « écrit… » si elle finit par se taire
            reply, trace = await self.__think(channel, author, query, note,
                                              typing=reply_to is not None)

            if reply is None:
                Log.info(f"Rosalie choisit de ne rien dire ({place_name(channel)})")
                if trace:   # elle a agi sans rien dire : on le garde en mémoire, et un ✅
                    bot.memory.add(channel.id, Entry(
                        author_id=bot.user.id, author_name=bot.user.display_name, content="",
                        is_bot=True, acted=True, tool_messages=trace, spontaneous=spontaneous))
                    if reply_to is not None:
                        await _react(reply_to, "✅")
                return None

            dedicated = bot.decider.is_dedicated(channel.id)
            sent = await _send(channel, reply, reply_to=None if dedicated else reply_to)
            Log.message(channel, reply, bot.user.name, bot.user.name)
            bot.memory.add(channel.id, Entry(
                author_id=bot.user.id,
                author_name=bot.user.display_name,
                content=reply,
                is_bot=True,
                message_id=sent.id,
                acted=bool(trace),
                tool_messages=trace,
                spontaneous=spontaneous,
            ))
            return reply

    async def __think(self, channel, author, query: str | None, note: str | None,
                      typing: bool) -> tuple[str | None, list[dict]]:
        """Réflexion + outils, puis, si elle a écrit un bloc run-python/run-bash : confirmation
        sur Discord, exécution, et elle reprend avec la sortie (jusqu'à CODE_MAX_RUNS fois)."""
        bot = self.__bot
        config = bot.config
        owner = bot.decider.is_owner(author.id)
        entries = bot.memory.get(channel.id)
        system = await self.system_prompt(channel, query=query, speaker=author.display_name,
                                          guest=not owner)
        messages = build_messages(system, entries, tools=True)
        if note:
            with_note(messages, note)
        ctx = ToolContext(bot=bot, channel=channel, author=author)
        trace: list[dict] = []
        runs = 0
        while True:
            async with channel.typing() if typing else contextlib.nullcontext():
                result = await run_agent(bot.llm, messages, ctx, max_steps=config.max_tool_steps,
                                         acted=runs > 0)
            if result.actions:
                Log.info("Actions: " + " | ".join(result.actions))
            trace += result.trace
            reply = clean_reply(result.text, bot.user.display_name)
            block = extract_code(reply) if owner and config.code_exec else None
            if block is None or runs >= config.code_max_runs:
                return (None if is_silence(reply) else reply), trace

            runs += 1
            if block.before:
                await channel.send(block.before[:2000])
            confirmed, shown = await ask_code_confirmation(
                channel, config.owner_ids, block.language, block.code)
            if not confirmed:
                Log.info("Code refusé par l'owner")
                trace += [{"role": "assistant", "content": reply},
                          {"role": "user", "content": REFUSED_NOTE}]
                return "D'accord, je ne l'exécute pas.", trace

            Log.command(f"run {block.language} ({len(block.code)} caractères)")
            async with channel.typing():
                outcome = await run_code(block, config.storage_dir / "workspace", config.code_timeout)
            Log.info(f"Code : {outcome.summary()}")
            output = outcome.output.replace("```", "`\u200b``")[:1800] or "(aucune sortie)"
            await shown.reply(f"{outcome.summary()}\n```\n{output}\n```", mention_author=False)

            note_message = {"role": "user", "content": result_note(outcome)}
            messages += [{"role": "assistant", "content": reply}, note_message]
            trace += [{"role": "assistant", "content": reply}, note_message]

    async def system_prompt(self, channel, query: str | None = None,
                            speaker: str | None = None, guest: bool = False) -> str:
        """Prompt système : persona + contexte + souvenirs (importants + liés au message).
        Pour un non-owner : aucun souvenir, aucune action."""
        bot = self.__bot
        if guest:
            return build_system_prompt(bot.persona.text, bot.user.display_name, place_name(channel),
                                       speaker=speaker, guest=True, web=bot.config.web_access)
        memories = {m.id: m for m in bot.long_term.core()}
        related = await bot.long_term.search(query, limit=5) if query else []
        for memory in related:
            memories.setdefault(memory.id, memory)
        return build_system_prompt(
            bot.persona.text, bot.user.display_name, place_name(channel),
            speaker=speaker,
            servers=[guild.name for guild in bot.guilds],
            memories=[memory.line() for memory in memories.values()],
            nothing_related=bool(query) and not related,
            followups=[f.line() for f in bot.agenda.pending(channel.id)],
            code_env=environment_line(bot.config.storage_dir / "workspace")
            if bot.config.code_exec else None,
        )


async def _send(channel, reply: str, reply_to: discord.Message | None) -> discord.Message:
    chunks = split_message(reply)
    if reply_to is not None and not isinstance(channel, discord.DMChannel):
        sent = await reply_to.reply(chunks[0], mention_author=False)
    else:
        sent = await channel.send(chunks[0])
    for chunk in chunks[1:]:
        sent = await channel.send(chunk)
    return sent


async def _react(message: discord.Message, emoji: str):
    try:
        await message.add_reaction(emoji)
    except discord.HTTPException:
        pass


def setup(bot):
    bot.add_cog(Chat(bot))
