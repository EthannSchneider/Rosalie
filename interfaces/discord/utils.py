"""Petits utilitaires Discord : description d'un salon, texte lisible d'un message."""
import discord

from libs.core.types import make_key


def place_name(channel: discord.abc.Messageable) -> str:
    if isinstance(channel, discord.DMChannel):
        return "en message privé"
    guild = getattr(channel, "guild", None)
    name = getattr(channel, "name", "salon")
    return f"salon #{name}" + (f" du serveur « {guild.name} »" if guild else "")


def message_text(message: discord.Message, bot_user: discord.ClientUser) -> str:
    """Contenu lisible : mentions -> pseudos, sans la mention du bot, pièces jointes signalées."""
    text = message.clean_content
    for prefix in (f"@{bot_user.display_name}", f"@{bot_user.name}"):
        text = text.replace(prefix, "")
    text = text.strip()
    for attachment in message.attachments:
        text += f" [pièce jointe : {attachment.filename}]"
    return text.strip()


def conversation_key(channel_or_ctx) -> str:
    """Clé mémoire d'un salon Discord (accepte un salon ou un ApplicationContext)."""
    channel = getattr(channel_or_ctx, "channel", None) or channel_or_ctx
    return make_key("discord", channel.id)


async def is_owner(bot: discord.Bot, user: discord.abc.User) -> bool:
    """Seuls les OWNER_IDS du .env peuvent commander Rosalie sur Discord."""
    return user.id in bot.rosalie.config.owner_ids
