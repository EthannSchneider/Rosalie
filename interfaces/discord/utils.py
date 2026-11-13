"""Petits utilitaires Discord : description d'un salon, texte lisible d'un message."""
import discord

from libs.core.types import make_key
from libs.models.role import PERMISSIONS, acts


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


def permissions_of(bot: discord.Bot, user: discord.abc.User) -> frozenset[str]:
    """Permissions du compte lié à cet identifiant Discord (libs/models/role.py)."""
    return bot.rosalie.discord_permissions(user.id)


async def is_owner(bot: discord.Bot, user: discord.abc.User) -> bool:
    """Elle agit pour cette personne : compte lié avec au moins une permission « act.* »."""
    return acts(permissions_of(bot, user))


async def require(ctx: discord.ApplicationContext, permission: str) -> bool:
    """Vérifie une permission pour une commande ; sinon répond (en privé) ce qu'il manque."""
    if permission in permissions_of(ctx.bot, ctx.author):
        return True
    await ctx.respond(f"Ton rôle n'a pas la permission « {PERMISSIONS[permission][0]} ».", ephemeral=True)
    return False
