import discord

from libs.log import Log
from interfaces.discord.utils import is_owner


class Reload(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.__bot = bot

    @discord.slash_command(name="reload", description="Recharger les commandes Discord")
    async def reload(self, ctx: discord.ApplicationContext):
        Log.command(ctx.author.name + " is launching reload command")
        if not await is_owner(self.__bot, ctx.author):
            await ctx.respond("You don't have permission to use this command.", ephemeral=True)
            return
        for extension in list(self.__bot.extensions):
            self.__bot.reload_extension(extension)
        Log.info("Reloaded all Discord cogs from " + str(self.__bot.user))
        await ctx.respond("Commandes Discord rechargées.", ephemeral=True)


def setup(bot):
    bot.add_cog(Reload(bot))
