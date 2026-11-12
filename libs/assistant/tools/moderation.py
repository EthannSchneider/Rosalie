"""Modération : rôles, surnoms, exclusion temporaire, expulsion, bannissement."""
import datetime

from libs.assistant.resolver import resolve_guild, resolve_member, resolve_role
from libs.assistant.tools.base import ToolContext, tool, _int


@tool("add_role", "Donne un rôle à un membre.",
      {"member": ("string", "Pseudo ou id du membre"), "role": ("string", "Nom du rôle"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member", "role"))
async def add_role(ctx: ToolContext, member: str, role: str, server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    target = await resolve_member(ctx.bot, member, guild)
    selected = resolve_role(guild, role)
    await target.add_roles(selected, reason=f"Demandé par {ctx.author}")
    return f"Rôle @{selected.name} donné à {target.display_name}."


@tool("remove_role", "Retire un rôle à un membre.",
      {"member": ("string", "Pseudo ou id du membre"), "role": ("string", "Nom du rôle"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member", "role"))
async def remove_role(ctx: ToolContext, member: str, role: str, server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    target = await resolve_member(ctx.bot, member, guild)
    selected = resolve_role(guild, role)
    await target.remove_roles(selected, reason=f"Demandé par {ctx.author}")
    return f"Rôle @{selected.name} retiré à {target.display_name}."


@tool("kick_member", "Expulse un membre du serveur.",
      {"member": ("string", "Pseudo ou id"), "reason": ("string", "Raison"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member",), confirm="Expulser « {member} »")
async def kick_member(ctx: ToolContext, member: str, reason: str = "", server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    target = await resolve_member(ctx.bot, member, guild)
    await target.kick(reason=reason or f"Demandé par {ctx.author}")
    return f"{target.display_name} a été expulsé de « {guild.name} »."


@tool("ban_member", "Bannit un membre du serveur.",
      {"member": ("string", "Pseudo ou id"), "reason": ("string", "Raison"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member",), confirm="Bannir « {member} »")
async def ban_member(ctx: ToolContext, member: str, reason: str = "", server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    target = await resolve_member(ctx.bot, member, guild)
    await guild.ban(target, reason=reason or f"Demandé par {ctx.author}")
    return f"{target.display_name} a été banni de « {guild.name} »."


@tool("timeout_member",
      "Exclut temporairement un membre (il ne peut plus écrire ni parler). minutes=0 lève l'exclusion.",
      {"member": ("string", "Pseudo ou id"),
       "minutes": ("integer", "Durée en minutes (0 à 40320 = 28 jours)"),
       "reason": ("string", "Raison"), "server": ("string", "Serveur (optionnel)")},
      required=("member", "minutes"), confirm="Exclure temporairement « {member} » ({minutes} min)")
async def timeout_member(ctx: ToolContext, member: str, minutes: int, reason: str = "",
                         server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    target = await resolve_member(ctx.bot, member, guild)
    minutes = _int(minutes, 10, 0, 40320)
    reason = reason or f"Demandé par {ctx.author}"
    if minutes == 0:
        await target.remove_timeout(reason=reason)
        return f"Exclusion de {target.display_name} levée."
    await target.timeout_for(datetime.timedelta(minutes=minutes), reason=reason)
    return f"{target.display_name} est exclu temporairement pour {minutes} min."


@tool("set_nickname", "Change le surnom d'un membre sur un serveur (vide = retirer le surnom).",
      {"member": ("string", "Pseudo ou id (« moi » = Rosalie elle-même)"),
       "nickname": ("string", "Nouveau surnom (vide = aucun)"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member",))
async def set_nickname(ctx: ToolContext, member: str, nickname: str | None = None,
                       server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    target = guild.me if member.strip().lower() in ("moi", "me", "rosalie") \
        else await resolve_member(ctx.bot, member, guild)
    await target.edit(nick=(nickname or None) and nickname[:32], reason=f"Demandé par {ctx.author}")
    return f"Surnom de {target.name} : {nickname or '(aucun)'}."
