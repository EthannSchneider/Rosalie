"""Helpers des outils Discord : accès au client, au salon courant, résolution de salons/messages."""
import re
from functools import partial

import discord

from interfaces.discord.resolver import HERE, ResolveError, _id, normalize, resolve_channel
from libs.assistant.tools.base import ToolContext, tool
from libs.core.types import make_key

# Les outils Discord ne sont proposés que si l'interface Discord tourne
discord_tool = partial(tool, requires="discord")


def client(ctx: ToolContext) -> discord.Bot:
    return ctx.interface("discord").client


def here(ctx: ToolContext):
    """Salon Discord où l'on parle (None si la conversation vient d'une autre interface)."""
    return ctx.conversation.native if ctx.conversation.interface == "discord" else None


def current_guild(ctx: ToolContext) -> discord.Guild | None:
    return getattr(here(ctx), "guild", None)


def reason(ctx: ToolContext) -> str:
    return f"Demandé par {ctx.person.display_name}"


async def find_channel(bot: discord.Bot, query: str | None, current, server: str | None = None,
                       messageable: bool = True):
    """resolve_channel + repli : un ID absent du cache est demandé à Discord (fils, DM…).
    current : salon Discord où l'on parle (None si on parle via une autre interface)."""
    if current is None and (not query or normalize(query) in HERE):
        raise ResolveError("on ne se parle pas sur Discord : précise le salon ou le serveur")
    try:
        return resolve_channel(bot, query, current, server, messageable=messageable)
    except ResolveError:
        channel_id = _id(query) if query else None
        if not channel_id:
            raise
    try:
        return await bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.InvalidData, AttributeError):
        raise ResolveError(f"l'identifiant {channel_id} ne correspond à aucun salon que je peux "
                           "voir (c'est peut-être l'ID d'un message ou d'une personne, ou un salon "
                           "d'un serveur où je ne suis pas). Utilise list_channels.") from None


async def _channel(ctx: ToolContext, query: str | None, server: str | None = None,
                   messageable: bool = True):
    return await find_channel(client(ctx), query, here(ctx), server, messageable)


_MESSAGE_LINK = re.compile(r"discord(?:app)?\.com/channels/(?:\d+|@me)/(\d+)/(\d+)")


async def _message(ctx: ToolContext, message: str, channel: str | None = None,
                   from_owner: bool = False) -> discord.Message:
    """Message par id, lien Discord, ou « dernier » (le plus récent du salon qui n'est pas
    de Rosalie ; « mon dernier » / from_owner=True : le plus récent de la personne qui parle)."""
    text = str(message or "").strip()
    link = _MESSAGE_LINK.search(text)
    if link:
        channel, text = link.group(1), link.group(2)
    target = await _channel(ctx, channel)
    lowered = text.lower()
    if "dernier" in lowered or lowered in ("last", "my last"):
        from_owner = from_owner or lowered.startswith(("mon ", "my "))
        me = getattr(client(ctx).user, "id", None)
        async for candidate in target.history(limit=30):
            if candidate.author.id != me and (not from_owner or candidate.author.id == ctx.person.id):
                return candidate
        raise ResolveError("aucun message récent trouvé dans ce salon")
    message_id = _id(text)
    if not message_id:
        raise ResolveError(f"« {message} » n'est pas un id ou un lien de message "
                           "(utilise read_messages pour voir les ids)")
    try:
        return await target.fetch_message(message_id)
    except discord.NotFound:
        raise ResolveError(f"message {message_id} introuvable dans ce salon") from None


def _remember_sent(ctx: ToolContext, sent: discord.Message, content: str):
    """Le message envoyé par un outil entre dans l'historique du salon de destination :
    si la personne répond, Rosalie sait ce qu'elle lui a écrit et pour qui."""
    channel = getattr(sent, "channel", None)
    if channel is not None:
        ctx.rosalie.remember_sent(make_key("discord", channel.id), content, sent.id,
                                  current=ctx.conversation.key)
