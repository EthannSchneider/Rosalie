"""Modération : rôles, surnoms, exclusion temporaire, expulsion, bannissement."""
import datetime

from interfaces.discord.resolver import resolve_guild, resolve_member, resolve_role
from interfaces.discord.tools.helpers import discord_tool, client, current_guild, reason
from libs.assistant.tools.base import ToolContext, _int


@discord_tool("add_role", "Donne un rôle à un membre.",
      {"member": ("string", "Pseudo ou id du membre"), "role": ("string", "Nom du rôle"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member", "role"))
async def add_role(ctx: ToolContext, member: str, role: str, server: str | None = None) -> str:
    guild = resolve_guild(client(ctx), server, current_guild(ctx))
    target = await resolve_member(client(ctx), member, guild)
    selected = resolve_role(guild, role)
    await target.add_roles(selected, reason=reason(ctx))
    return f"Rôle @{selected.name} donné à {target.display_name}."


@discord_tool("remove_role", "Retire un rôle à un membre.",
      {"member": ("string", "Pseudo ou id du membre"), "role": ("string", "Nom du rôle"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member", "role"))
async def remove_role(ctx: ToolContext, member: str, role: str, server: str | None = None) -> str:
    guild = resolve_guild(client(ctx), server, current_guild(ctx))
    target = await resolve_member(client(ctx), member, guild)
    selected = resolve_role(guild, role)
    await target.remove_roles(selected, reason=reason(ctx))
    return f"Rôle @{selected.name} retiré à {target.display_name}."


@discord_tool("kick_member", "Expulse un membre du serveur.",
      {"member": ("string", "Pseudo ou id"), "reason": ("string", "Raison"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member",), confirm="Expulser « {member} »")
async def kick_member(ctx: ToolContext, member: str, reason: str = "", server: str | None = None) -> str:
    guild = resolve_guild(client(ctx), server, current_guild(ctx))
    target = await resolve_member(client(ctx), member, guild)
    await target.kick(reason=reason or reason(ctx))
    return f"{target.display_name} a été expulsé de « {guild.name} »."


@discord_tool("ban_member", "Bannit un membre du serveur.",
      {"member": ("string", "Pseudo ou id"), "reason": ("string", "Raison"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member",), confirm="Bannir « {member} »")
async def ban_member(ctx: ToolContext, member: str, reason: str = "", server: str | None = None) -> str:
    guild = resolve_guild(client(ctx), server, current_guild(ctx))
    target = await resolve_member(client(ctx), member, guild)
    await guild.ban(target, reason=reason or reason(ctx))
    return f"{target.display_name} a été banni de « {guild.name} »."


@discord_tool("timeout_member",
      "Exclut temporairement un membre (il ne peut plus écrire ni parler). minutes=0 lève l'exclusion.",
      {"member": ("string", "Pseudo ou id"),
       "minutes": ("integer", "Durée en minutes (0 à 40320 = 28 jours)"),
       "reason": ("string", "Raison"), "server": ("string", "Serveur (optionnel)")},
      required=("member", "minutes"), confirm="Exclure temporairement « {member} » ({minutes} min)")
async def timeout_member(ctx: ToolContext, member: str, minutes: int, reason: str = "",
                         server: str | None = None) -> str:
    guild = resolve_guild(client(ctx), server, current_guild(ctx))
    target = await resolve_member(client(ctx), member, guild)
    minutes = _int(minutes, 10, 0, 40320)
    reason = reason or reason(ctx)
    if minutes == 0:
        await target.remove_timeout(reason=reason)
        return f"Exclusion de {target.display_name} levée."
    await target.timeout_for(datetime.timedelta(minutes=minutes), reason=reason)
    return f"{target.display_name} est exclu temporairement pour {minutes} min."


@discord_tool("set_nickname", "Change le surnom d'un membre sur un serveur (vide = retirer le surnom).",
      {"member": ("string", "Pseudo ou id (« moi » = Rosalie elle-même)"),
       "nickname": ("string", "Nouveau surnom (vide = aucun)"),
       "server": ("string", "Serveur (optionnel)")},
      required=("member",))
async def set_nickname(ctx: ToolContext, member: str, nickname: str | None = None,
                       server: str | None = None) -> str:
    guild = resolve_guild(client(ctx), server, current_guild(ctx))
    target = guild.me if member.strip().lower() in ("moi", "me", "rosalie") \
        else await resolve_member(client(ctx), member, guild)
    await target.edit(nick=(nickname or None) and nickname[:32], reason=reason(ctx))
    return f"Surnom de {target.name} : {nickname or '(aucun)'}."
