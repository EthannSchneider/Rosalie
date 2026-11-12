"""Socle des outils : contexte, registre, décorateur @tool, exécution sécurisée, helpers."""
import json
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

import discord

from libs.assistant.confirm import ask_confirmation
from libs.assistant.resolver import ResolveError, _id, resolve_channel
from libs.conversation.memory import Entry
from libs.log import Log


@dataclass
class ToolContext:
    bot: discord.Bot
    channel: discord.abc.Messageable   # salon où l'ordre a été donné
    author: discord.abc.User

    @property
    def is_owner(self) -> bool:
        return self.author.id in self.bot.config.owner_ids

    @property
    def guild(self) -> discord.Guild | None:
        return getattr(self.channel, "guild", None)


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, tuple[str, str]]          # nom -> (type JSON, description)
    required: tuple[str, ...]
    func: Callable[..., Awaitable[str]]
    confirm: str | None = None                  # texte de confirmation => outil dangereux

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {name: {"type": kind, "description": desc}
                               for name, (kind, desc) in self.params.items()},
                "required": list(self.required),
            },
        }}


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, params: dict | None = None,
         required: tuple[str, ...] = (), confirm: str | None = None):
    def decorator(func):
        TOOLS[name] = Tool(name, description, params or {}, required, func, confirm)
        return func
    return decorator


WEB_TOOLS = {"web_search", "fetch_url", "send_image", "send_image_url", "weather"}
# Seuls outils permis quand ce n'est pas un owner qui parle : chercher une info, rien d'autre
GUEST_TOOLS = {"web_search", "fetch_url", "weather"}


def schemas(web_access: bool = True, guest: bool = False,
            disabled: tuple[str, ...] | frozenset[str] = ()) -> list[dict]:
    return [t.schema() for t in TOOLS.values()
            if (web_access or t.name not in WEB_TOOLS) and (not guest or t.name in GUEST_TOOLS)
            and t.name not in disabled]


async def execute(ctx: ToolContext, name: str, arguments: dict | str | None) -> str:
    """Exécute un appel d'outil et renvoie un texte pour le LLM (jamais d'exception)."""
    selected = TOOLS.get(name)
    if selected is None:
        return f"Erreur : l'outil « {name} » n'existe pas."
    if name in getattr(ctx.bot.config, "disabled_tools", ()):
        return f"Erreur : l'outil « {name} » est désactivé (DISABLED_TOOLS)."
    if name not in GUEST_TOOLS and not ctx.is_owner:
        Log.warning(f"Tool {name} refused for non-owner {ctx.author}")
        return "Erreur : seul mon créateur peut me demander ça."
    if name in WEB_TOOLS and not getattr(ctx.bot.config, "web_access", True):
        return "Erreur : l'accès internet est désactivé (WEB_ACCESS=false)."
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return "Erreur : arguments JSON invalides."
    arguments = {k: v for k, v in (arguments or {}).items()
                 if k in selected.params and v not in (None, "")}
    missing = [r for r in selected.required if r not in arguments]
    if missing:
        return f"Erreur : paramètre(s) manquant(s) : {', '.join(missing)}."

    try:
        if selected.confirm:
            text = selected.confirm.format_map(_Default(arguments))
            if not await ask_confirmation(ctx.channel, ctx.bot.config.owner_ids, text):
                return "Action annulée : l'utilisateur n'a pas confirmé."
        result = await selected.func(ctx, **arguments)
    except ResolveError as error:
        result = f"Erreur : {error}"
    except discord.Forbidden:
        result = "Erreur : je n'ai pas la permission Discord pour faire ça."
    except discord.HTTPException as error:
        result = f"Erreur Discord : {error.text or error}"
    except (TypeError, ValueError) as error:
        result = f"Erreur : arguments invalides ({error})."
    Log.command(f"tool {name}({arguments}) -> {result[:200]}")
    return result


class _Default(dict):
    def __missing__(self, key):
        return "?"


def _int(value, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


async def _channel(ctx: ToolContext, query: str | None, server: str | None = None,
                   messageable: bool = True):
    """resolve_channel + repli : un ID absent du cache est demandé à Discord (fils, DM…)."""
    try:
        return resolve_channel(ctx.bot, query, ctx.channel, server, messageable=messageable)
    except ResolveError:
        channel_id = _id(query) if query else None
        if not channel_id:
            raise
    try:
        return await ctx.bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.InvalidData, AttributeError):
        raise ResolveError(f"l'identifiant {channel_id} ne correspond à aucun salon que je peux "
                           "voir (c'est peut-être l'ID d'un message ou d'une personne, ou un salon "
                           "d'un serveur où je ne suis pas). Utilise list_channels.") from None


_MESSAGE_LINK = re.compile(r"discord(?:app)?\.com/channels/(?:\d+|@me)/(\d+)/(\d+)")


async def _message(ctx: ToolContext, message: str, channel: str | None = None,
                   from_owner: bool = False) -> discord.Message:
    """Message par id, lien Discord, ou « dernier » (le plus récent du salon qui n'est pas
    de Rosalie ; from_owner=True : le plus récent de la personne qui parle)."""
    text = str(message or "").strip()
    link = _MESSAGE_LINK.search(text)
    if link:
        channel, text = link.group(1), link.group(2)
    target = await _channel(ctx, channel)
    lowered = text.lower()
    if "dernier" in lowered or lowered in ("last", "my last"):
        from_owner = from_owner or lowered.startswith(("mon ", "my "))
        me = getattr(ctx.bot.user, "id", None)
        async for candidate in target.history(limit=30):
            if candidate.author.id != me and (not from_owner or candidate.author.id == ctx.author.id):
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
    memory = getattr(ctx.bot, "memory", None)
    channel = getattr(sent, "channel", None)
    if memory is None or channel is None or channel.id == getattr(ctx.channel, "id", None):
        return   # même salon : la réponse finale y est déjà enregistrée

    me = ctx.bot.user
    memory.add(channel.id, Entry(
        author_id=me.id, author_name=me.display_name,
        content=content,
        is_bot=True, message_id=sent.id, acted=True))
