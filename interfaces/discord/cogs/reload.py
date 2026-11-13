import discord

from libs.log import Log
from interfaces.discord.utils import require


class Reload(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.__bot = bot

    @discord.slash_command(name="reload", description="Recharger les commandes Discord")
    async def reload(self, ctx: discord.ApplicationContext):
        Log.command(ctx.author.name + " is launching reload command")
        if not await require(ctx, "settings"):
            return
        for extension in list(self.__bot.extensions):
            self.__bot.reload_extension(extension)
        Log.info("Reloaded all Discord cogs from " + str(self.__bot.user))
        await ctx.respond("Commandes Discord rechargées.", ephemeral=True)


def setup(bot):
    bot.add_cog(Reload(bot))
