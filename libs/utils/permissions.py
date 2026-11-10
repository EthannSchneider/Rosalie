import discord


async def is_owner(bot: discord.Bot, user: discord.abc.User) -> bool:
    """Seuls les OWNER_IDS du .env peuvent commander Gideon."""
    return user.id in bot.config.owner_ids
