"""Modération : rôles, expulsion, bannissement."""
from libs.assistant.resolver import resolve_guild, resolve_member, resolve_role
from libs.assistant.tools.base import ToolContext, tool


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
