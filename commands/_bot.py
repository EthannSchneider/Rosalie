import asyncio
import os

import discord

from libs.browser import VirtualBrowser
from libs.config import ROOT_DIR, Config
from libs.conversation.decider import ReplyDecider
from libs.conversation.memory import ConversationMemory
from libs.dataset.store import DatasetStore
from libs.llm.ollama import OllamaClient
from libs.llm.persona import Persona
from libs.log import Log
from libs import web
from libs.memory.long_term import LongTermMemory
from libs.settings import Settings


def run_bot(bot_name: str):
    asyncio.run(_run_bot(bot_name))


def _load_cogs(bot: discord.Bot, bot_name: str):
    cogs_dir = ROOT_DIR / "cogs"

    # Cogs spécifiques au bot
    for path in sorted((cogs_dir / bot_name).glob("*.py")):
        if not path.name.startswith("_"):
            bot.load_extension(f"cogs.{bot_name}.{path.stem}")

    # Cogs communs
    for path in sorted(cogs_dir.glob("*.py")):
        if not path.name.startswith("_"):
            bot.load_extension(f"cogs.{path.stem}")


def build_bot(config: Config) -> discord.Bot:
    intents = discord.Intents.default()
    intents.message_content = True  # Developer Portal : « Message Content Intent »
    intents.members = True          # Developer Portal : « Server Members Intent » (retrouver un membre par pseudo)

    bot = discord.Bot(intents=intents)

    # Services partagés, accessibles depuis les cogs via self.bot.<service>
    bot.config = config
    bot.settings = Settings(config.storage_dir / "settings.json")
    bot.persona = Persona(config.persona_file)
    bot.llm = OllamaClient(
        base_url=config.ollama_url,
        model=bot.settings.model or config.ollama_model,
        keep_alive=config.ollama_keep_alive,
        options={"num_ctx": config.num_ctx, "temperature": config.temperature},
    )
    bot.memory = ConversationMemory(config.storage_dir / "memory", config.history_size)
    bot.long_term = LongTermMemory(config.storage_dir / "long_term.sqlite3", bot.llm, config.embed_model)
    bot.dataset = DatasetStore(config.storage_dir / "dataset" / "samples.jsonl")
    bot.decider = ReplyDecider(config, bot.llm, bot.settings)
    bot.browser = VirtualBrowser(web.USER_AGENT) if config.web_access and config.web_browser != "never" else None
    return bot


async def _run_bot(bot_name: str):
    config = Config.from_env()
    token_name = bot_name.upper() + "_TOKEN"
    token = os.getenv(token_name)
    if not token:
        Log.error(token_name + " is not defined in .env file")
        return
    if not config.owner_ids:
        Log.error("OWNER_IDS is empty: Gideon n'obéit qu'aux owners, elle ne répondrait à personne.")
        return

    bot = build_bot(config)
    _load_cogs(bot, bot_name)

    @bot.event
    async def on_ready():
        Log.info(f"{bot_name.capitalize()} start with {bot.user} : {bot.user.id}"
                 f" (model: {bot.llm.model}, souvenirs: {bot.long_term.count()})")

    try:
        await bot.start(token)
    finally:
        await bot.llm.close()
        if bot.browser:
            await bot.browser.close()
        bot.long_term.close()
        if not bot.is_closed():
            await bot.close()
