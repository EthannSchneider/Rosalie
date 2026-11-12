"""Relaie les événements Discord au cœur de Rosalie."""
import discord

from libs.core.types import make_key


class Events(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @discord.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await self.bot.rosalie.receive(await self.bot.interface.incoming_from(message))

    @discord.Cog.listener()
    async def on_typing(self, channel, user, when):
        """Tu es en train d'écrire la suite : elle attend encore un peu."""
        self.bot.rosalie.typing_from(make_key("discord", channel.id), make_key("discord", user.id))


def setup(bot):
    bot.add_cog(Events(bot))
