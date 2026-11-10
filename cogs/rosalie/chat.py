import asyncio
import traceback
from collections import defaultdict

import discord

from libs.assistant.agent import run_agent
from libs.assistant.tools import ToolContext
from libs.conversation.memory import Entry
from libs.conversation.prompt import build_messages, build_system_prompt, clean_reply
from libs.llm.ollama import OllamaError
from libs.log import Log
from libs.memory.extractor import extract_memories
from libs.utils.discord_utils import message_text, place_name, split_message


class Chat(discord.Cog):
    """Écoute les messages des owners, fait agir Rosalie et répond."""

    def __init__(self, bot: discord.Bot):
        self.__bot = bot
        self.__locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.__background: set[asyncio.Task] = set()

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
        if not decision:
            Log.info(f"Not replying to {message.author.name} ({decision.reason})")
            return

        Log.info(f"Replying to {message.author.name} ({decision.reason})")

        async with self.__locks[channel_id]:
            try:
                async with message.channel.typing():
                    reply, acted = await self.respond(message)
            except OllamaError as error:
                Log.error(f"Ollama error: {error}")
                await message.reply("Je n'arrive pas à joindre mon cerveau… Ollama est lancé ?",
                                    mention_author=False)
                return
            except Exception as error:
                Log.error(f"{error}\n{traceback.format_exc()}")
                await message.reply(f"Oups, j'ai planté : `{error}`", mention_author=False)
                return

            sent = await self.__send(message, reply, reply_to=not bot.decider.is_dedicated(channel_id))
            Log.message(message.channel, reply, bot.user.name, bot.user.name)
            bot.memory.add(channel_id, Entry(
                author_id=bot.user.id,
                author_name=bot.user.display_name,
                content=reply,
                is_bot=True,
                message_id=sent.id,
                acted=acted,
            ))
            bot.decider.mark_active(channel_id, message.author.id)

        if not bot.decider.is_owner(message.author.id):
            return   # on ne prend des notes que sur les owners
        # Prise de notes automatique, sans bloquer la conversation
        task = asyncio.create_task(extract_memories(
            bot.llm, bot.config.decider_model, bot.long_term,
            message.author.display_name, message_text(message, bot.user), reply))
        self.__background.add(task)
        task.add_done_callback(self.__background.discard)

    async def respond(self, message: discord.Message) -> tuple[str, bool]:
        bot = self.__bot
        entries = bot.memory.get(message.channel.id)
        system = await self.system_prompt(message.channel, query=message.content,
                                          speaker=message.author.display_name,
                                          guest=not bot.decider.is_owner(message.author.id))
        ctx = ToolContext(bot=bot, channel=message.channel, author=message.author)
        result = await run_agent(bot.llm, build_messages(system, entries), ctx,
                                 max_steps=bot.config.max_tool_steps)
        reply = clean_reply(result.text, bot.user.display_name)
        if not reply:
            reply = "C'est fait." if result.actions else "…"
        if result.actions:
            Log.info("Actions: " + " | ".join(result.actions))
        return reply, bool(result.actions)

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
        )

    @staticmethod
    async def __send(message: discord.Message, reply: str, reply_to: bool) -> discord.Message:
        chunks = split_message(reply)
        if reply_to and not isinstance(message.channel, discord.DMChannel):
            sent = await message.reply(chunks[0], mention_author=False)
        else:
            sent = await message.channel.send(chunks[0])
        for chunk in chunks[1:]:
            sent = await message.channel.send(chunk)
        return sent


def setup(bot):
    bot.add_cog(Chat(bot))
