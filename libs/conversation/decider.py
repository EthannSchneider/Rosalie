import re
import time
from dataclasses import dataclass

import discord

from libs.config import Config
from libs.conversation.memory import Entry
from libs.llm.ollama import OllamaClient, OllamaError
from libs.log import Log


@dataclass
class Decision:
    reply: bool
    reason: str
    record: bool = False  # garder le message dans l'historique même sans répondre

    def __bool__(self):
        return self.reply


JUDGE_PROMPT = (
    "Tu analyses une conversation Discord. {name} est une assistante IA présente dans le salon.\n"
    "Réponds UNIQUEMENT par OUI ou NON.\n"
    "OUI si le dernier message s'adresse à {name}, continue la discussion avec {name}, "
    "ou attend clairement une réaction de {name}.\n"
    "NON si le dernier message s'adresse à quelqu'un d'autre, clôt la discussion "
    "(ex: « ok », « à plus »), ou n'a pas besoin de réponse."
)


class ReplyDecider:
    """Décide si Gideon doit répondre à un message.

    Ordre des règles (de la moins chère à la plus chère) :
      1. filtres durs : bots, tout le monde sauf OWNER_IDS, préfixes ignorés
      2. signaux explicites : DM, @mention, réponse à un de ses messages, son nom
      3. salon dédié : répond à tout (sauf si on parle clairement à quelqu'un d'autre)
      4. conversation en cours avec cette personne (< CONVERSATION_TIMEOUT s) :
         un petit appel LLM « OUI/NON » tranche les cas ambigus
    """

    def __init__(self, config: Config, llm: OllamaClient, settings):
        self.__config = config
        self.__llm = llm
        self.__settings = settings
        self.__active: dict[tuple[int, int], float] = {}
        names = "|".join(re.escape(name) for name in config.names)
        self.__name_regex = re.compile(rf"(?<!\w)({names})(?!\w)", re.IGNORECASE)

    # --- état des conversations -------------------------------------------
    def mark_active(self, channel_id: int, user_id: int):
        self.__active[(channel_id, user_id)] = time.time()

    def is_active(self, channel_id: int, user_id: int) -> bool:
        last = self.__active.get((channel_id, user_id))
        return last is not None and time.time() - last < self.__config.conversation_timeout

    def stop(self, channel_id: int):
        for key in [key for key in self.__active if key[0] == channel_id]:
            del self.__active[key]

    def is_dedicated(self, channel_id: int) -> bool:
        return channel_id in self.__config.channel_ids or channel_id in self.__settings.channel_ids

    # --- décision ----------------------------------------------------------
    async def decide(self, message: discord.Message, bot_user: discord.ClientUser,
                     history: list[Entry]) -> Decision:
        config = self.__config
        content = message.content.strip()
        channel_id = message.channel.id

        if message.author.bot:
            return Decision(False, "author is a bot")
        if message.author.id not in config.owner_ids:
            return Decision(False, "not an owner")
        if not content and not message.attachments:
            return Decision(False, "empty message")
        if content.startswith(config.ignore_prefixes):
            return Decision(False, "ignored prefix")

        if isinstance(message.channel, discord.DMChannel):
            return Decision(True, "DM", record=True)
        if bot_user in message.mentions:
            return Decision(True, "mention", record=True)

        replied_to = await self.__replied_author(message)
        if replied_to is not None:
            if replied_to == bot_user.id:
                return Decision(True, "reply to Gideon", record=True)
            return Decision(False, "reply to someone else", record=self.is_dedicated(channel_id))

        talks_to_someone_else = any(
            user.id != bot_user.id for user in message.mentions)
        named = self.__name_regex.search(content) is not None

        if named:
            return Decision(True, "name", record=True)
        if talks_to_someone_else:
            return Decision(False, "mentions someone else", record=self.is_dedicated(channel_id))
        if self.is_dedicated(channel_id):
            return Decision(True, "dedicated channel", record=True)
        if self.is_active(channel_id, message.author.id):
            if not config.use_llm_decider:
                return Decision(True, "active conversation", record=True)
            wants = await self.__ask_judge(bot_user.display_name, history, message)
            return Decision(wants, f"active conversation, judge={'OUI' if wants else 'NON'}",
                            record=True)
        return Decision(False, "not addressed")

    async def __replied_author(self, message: discord.Message) -> int | None:
        reference = message.reference
        if reference is None or reference.message_id is None:
            return None
        resolved = reference.resolved
        if isinstance(resolved, discord.Message):
            return resolved.author.id
        try:
            original = await message.channel.fetch_message(reference.message_id)
            return original.author.id
        except discord.HTTPException:
            return None

    async def __ask_judge(self, bot_name: str, history: list[Entry],
                          message: discord.Message) -> bool:
        transcript = "\n".join(
            f"{bot_name if entry.is_bot else entry.author_name}: {entry.content}"
            for entry in history[-8:])
        prompt = (f"Conversation récente :\n{transcript}\n\n"
                  f"Dernier message — {message.author.display_name}: {message.content}\n\n"
                  f"{bot_name} doit-elle répondre ? (OUI/NON)")
        try:
            answer = await self.__llm.chat(
                [{"role": "system", "content": JUDGE_PROMPT.format(name=bot_name)},
                 {"role": "user", "content": prompt}],
                model=self.__config.decider_model,
                options={"temperature": 0, "num_predict": 3},
            )
        except OllamaError as error:
            Log.warning(f"Judge failed ({error}), defaulting to reply")
            return True
        return answer.strip().upper().startswith(("OUI", "YES"))
