"""Retrouve serveurs / salons / membres / rôles à partir de ce que le LLM écrit
(« Le bunker », « #général », un ID, une mention <#123>…)."""
import re
import unicodedata

import discord

from libs.assistant.tools.base import ToolError


class ResolveError(ToolError):
    """Cible introuvable ou ambiguë : le message est renvoyé au modèle."""


ID_REGEX = re.compile(r"\d{15,20}")
HERE = {"ici", "here", "cesalon", "salonactuel", "current"}
DEFAULT_CHANNEL_NAMES = ("general", "général", "bienvenue", "welcome", "accueil", "chat")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(char for char in text.lower() if char.isalnum())


def _id(query) -> int | None:
    match = ID_REGEX.search(str(query or ""))
    return int(match.group()) if match else None


def _exact(query, items, names):
    target = normalize(query)
    return [item for item in items if target and any(normalize(n) == target for n in names(item))]


def _contains(query, items, names):
    target = normalize(query)
    return [item for item in items if target and any(target in normalize(n) for n in names(item))]


def _single(matches, query, kind, label):
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    options = ", ".join(label(item) for item in matches[:10])
    raise ResolveError(f"Plusieurs {kind}s correspondent à « {query} » : {options}. "
                       "Demande lequel à l'utilisateur.")


def _pick(query, items, names, kind, label):
    for finder in (_exact, _contains):
        found = _single(finder(query, items, names), query, kind, label)
        if found is not None:
            return found
    raise ResolveError(f"Aucun {kind} ne correspond à « {query} ».")


def _guild_label(guild):
    return f"« {guild.name} »"


def _channel_label(channel):
    return f"#{channel.name} (serveur « {channel.guild.name} »)"


def resolve_guild(bot: discord.Bot, query: str | None, current: discord.Guild | None) -> discord.Guild:
    if not query:
        if current:
            return current
        if len(bot.guilds) == 1:
            return bot.guilds[0]
        raise ResolveError("Précise le serveur. Serveurs disponibles : "
                           + ", ".join(_guild_label(g) for g in bot.guilds))
    guild_id = _id(query)
    if guild_id and (guild := bot.get_guild(guild_id)):
        return guild
    return _pick(query, bot.guilds, lambda g: [g.name], "serveur", _guild_label)


def default_channel(guild: discord.Guild) -> discord.TextChannel:
    me = guild.me
    writable = [c for c in guild.text_channels if c.permissions_for(me).send_messages]
    if guild.system_channel in writable:
        return guild.system_channel
    for name in DEFAULT_CHANNEL_NAMES:
        for channel in writable:
            if normalize(name) in normalize(channel.name):
                return channel
    if writable:
        return writable[0]
    raise ResolveError(f"Je ne peux écrire dans aucun salon du serveur « {guild.name} ».")


def resolve_channel(bot: discord.Bot, query: str | None, current_channel,
                    server: str | None = None, messageable: bool = True):
    """Salon par ID/mention/nom. Si le nom correspond à un serveur, prend son salon principal."""
    if not query or normalize(query) in HERE:
        return current_channel
    channel_id = _id(query)
    if channel_id and (channel := bot.get_channel(channel_id)):
        return channel

    query = str(query).strip()
    if "/" in query and not server:
        server, query = (part.strip() for part in query.split("/", 1))
    query = query.lstrip("#")

    current_guild = getattr(current_channel, "guild", None)
    guilds = [resolve_guild(bot, server, current_guild)] if server else bot.guilds
    channels = [c for g in guilds for c in g.channels
                if not isinstance(c, discord.CategoryChannel)
                and (not messageable or hasattr(c, "send"))]
    names = lambda c: [c.name]

    # Priorité : salon exact > serveur exact > salon partiel > serveur partiel
    found = _single(_exact(query, channels, names), query, "salon", _channel_label)
    if found:
        return found
    if messageable and not server:
        guild = _single(_exact(query, bot.guilds, lambda g: [g.name]), query, "serveur", _guild_label)
        if guild:
            return default_channel(guild)
    found = _single(_contains(query, channels, names), query, "salon", _channel_label)
    if found:
        return found
    if messageable and not server:
        guild = _single(_contains(query, bot.guilds, lambda g: [g.name]), query, "serveur", _guild_label)
        if guild:
            return default_channel(guild)
    raise ResolveError(f"Aucun salon ou serveur ne correspond à « {query} ». "
                       "Utilise list_channels pour voir les salons.")


def _member_names(member):
    return [member.display_name, member.name, getattr(member, "global_name", None) or member.name]


async def resolve_member(bot: discord.Bot, query: str, guild: discord.Guild | None) -> discord.Member:
    member_id = _id(query)
    guilds = [guild] if guild else bot.guilds
    if member_id:
        for g in guilds:
            member = g.get_member(member_id)
            if member is None:
                try:
                    member = await g.fetch_member(member_id)
                except discord.HTTPException:
                    continue
            return member
        raise ResolveError(f"Membre {member_id} introuvable.")
    members = {m.id: m for g in guilds for m in g.members}
    return _pick(str(query).lstrip("@"), list(members.values()), _member_names, "membre",
                 lambda m: f"{m.display_name} (@{m.name})")


async def resolve_user(bot: discord.Bot, query: str) -> discord.abc.User:
    user_id = _id(query)
    if user_id:
        user = bot.get_user(user_id)
        if user is None:
            try:
                user = await bot.fetch_user(user_id)
            except discord.HTTPException as error:
                raise ResolveError(f"Utilisateur {user_id} introuvable.") from error
        return user
    return await resolve_member(bot, query, None)


def resolve_role(guild: discord.Guild, query: str) -> discord.Role:
    role_id = _id(query)
    if role_id and (role := guild.get_role(role_id)):
        return role
    roles = [r for r in guild.roles if not r.is_default()]
    return _pick(str(query).lstrip("@"), roles, lambda r: [r.name], "rôle", lambda r: f"@{r.name}")
