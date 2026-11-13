import re
import time
from dataclasses import dataclass
from typing import Callable

from libs.config import Config
from libs.core.types import Incoming
from libs.conversation.memory import Entry
from libs.llm.ollama import OllamaClient, OllamaError
from libs.log import Log


@dataclass
class Decision:
    reply: bool
    reason: str
    record: bool = False  # garder le message dans l'historique même sans répondre
    direct: bool = False  # on lui parle directement (DM, mention, nom, réponse) : elle doit répondre

    def __bool__(self):
        return self.reply


JUDGE_PROMPT = (
    "Tu analyses une conversation de groupe. {name} est une assistante IA qui y participe.\n"
    "Réponds UNIQUEMENT par OUI ou NON.\n"
    "OUI si le dernier message s'adresse à {name}, continue la discussion avec {name}, "
    "ou attend clairement une réaction de {name}.\n"
    "NON si le dernier message s'adresse à quelqu'un d'autre, clôt la discussion "
    "(ex: « ok », « à plus »), ou n'a pas besoin de réponse."
)


class ReplyDecider:
    """Décide si Rosalie doit répondre à un message, quelle que soit l'interface.

    Ordre des règles (de la moins chère à la plus chère) :
      1. filtres durs : préfixes ignorés, message vide, non-owners si PUBLIC_REPLIES=false
         (les non-owners ont droit à la discussion seulement, avec un délai anti-spam)
      2. signaux directs : tête-à-tête (DM, terminal), @mention, réponse à un de ses messages,
         son nom → elle DOIT répondre (direct=True)
      3. conversation dédiée : répond à tout (sauf si on parle clairement à quelqu'un d'autre)
      4. conversation en cours avec cette personne (< CONVERSATION_TIMEOUT s) :
         un petit appel LLM « OUI/NON » tranche les cas ambigus
    """

    def __init__(self, config: Config | Callable[[], Config], llm: OllamaClient, settings):
        # Une fonction qui donne les réglages actuels (ils peuvent changer à chaud)
        self.__source = config if callable(config) else (lambda: config)
        self.__llm = llm
        self.__settings = settings
        self.__active: dict[tuple[str, str], float] = {}
        self.__guest_replies: dict[str, float] = {}
        self.__regex_for: tuple[str, ...] = ()
        self.__regex: re.Pattern | None = None

    @property
    def __config(self) -> Config:
        return self.__source()

    @property
    def __name_regex(self) -> re.Pattern:
        names = self.__config.names
        if self.__regex is None or names != self.__regex_for:
            pattern = "|".join(re.escape(name) for name in names)
            self.__regex_for, self.__regex = names, re.compile(rf"(?<!\w)({pattern})(?!\w)", re.IGNORECASE)
        return self.__regex

    # --- état des conversations (clés « interface:id ») ----------------------------------
    def mark_active(self, conversation: str, person: str):
        self.__active[(conversation, person)] = time.time()

    def is_active(self, conversation: str, person: str) -> bool:
        last = self.__active.get((conversation, person))
        return last is not None and time.time() - last < self.__config.conversation_timeout

    def stop(self, conversation: str):
        for key in [key for key in self.__active if key[0] == conversation]:
            del self.__active[key]

    def is_dedicated(self, conversation: str) -> bool:
        return conversation in self.__config.dedicated or conversation in self.__settings.dedicated

    # --- décision ----------------------------------------------------------------------
    async def decide(self, incoming: Incoming, history: list[Entry]) -> Decision:
        decision = await self.__decide(incoming, history)
        if decision and not incoming.author.is_owner:
            now = time.time()
            key = incoming.author.key
            if now - self.__guest_replies.get(key, 0) < self.__config.public_cooldown:
                return Decision(False, "guest cooldown", record=decision.record)
            self.__guest_replies[key] = now
        return decision

    async def __decide(self, incoming: Incoming, history: list[Entry]) -> Decision:
        config = self.__config
        content = incoming.text.strip()
        conversation = incoming.conversation.key
        dedicated = self.is_dedicated(conversation)

        if not incoming.author.is_owner and not config.public_replies:
            return Decision(False, "not an owner")
        if not content and not incoming.has_attachments and not incoming.mentioned:
            return Decision(False, "empty message")
        if content.startswith(config.ignore_prefixes):
            return Decision(False, "ignored prefix")

        if incoming.conversation.private:
            return Decision(True, "private", record=True, direct=True)
        if incoming.mentioned:
            return Decision(True, "mention", record=True, direct=True)
        if incoming.reply_to_bot is True:
            return Decision(True, "reply to Rosalie", record=True, direct=True)
        if incoming.reply_to_bot is False:
            return Decision(False, "reply to someone else", record=dedicated)
        if self.__name_regex.search(content):
            return Decision(True, "name", record=True, direct=True)
        if incoming.mentions_other:
            return Decision(False, "mentions someone else", record=dedicated)
        if dedicated:
            return Decision(True, "dedicated", record=True)
        if self.is_active(conversation, incoming.author.key):
            if not config.use_llm_decider:
                return Decision(True, "active conversation", record=True)
            wants = await self.__ask_judge(self.__config.names[0].capitalize(), history, incoming)
            return Decision(wants, f"active conversation, judge={'OUI' if wants else 'NON'}",
                            record=True)
        return Decision(False, "not addressed")

    async def __ask_judge(self, bot_name: str, history: list[Entry],
                          incoming: Incoming) -> bool:
        transcript = "\n".join(
            f"{bot_name if entry.is_bot else entry.author_name}: {entry.content}"
            for entry in history[-8:])
        prompt = (f"Conversation récente :\n{transcript}\n\n"
                  f"Dernier message — {incoming.author.display_name}: {incoming.text}\n\n"
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
