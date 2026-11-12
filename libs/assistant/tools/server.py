"""Serveurs : lister serveurs, salons et membres, créer/supprimer un salon, statut."""
import discord

from libs.assistant.resolver import resolve_guild, resolve_role
from libs.assistant.tools.base import ToolContext, tool, _channel


@tool("list_servers", "Liste les serveurs Discord où Rosalie est présente.")
async def list_servers(ctx: ToolContext) -> str:
    return "\n".join(f"- {g.name} (id {g.id}, {g.member_count} membres)" for g in ctx.bot.guilds) \
        or "Aucun serveur."


@tool("list_channels", "Liste les salons d'un serveur.",
      {"server": ("string", "Nom ou id du serveur (vide = serveur actuel)")})
async def list_channels(ctx: ToolContext, server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    lines = []
    for category, channels in guild.by_category():
        lines.append(f"[{category.name if category else 'sans catégorie'}]")
        for channel in channels:
            kind = "vocal" if isinstance(channel, discord.VoiceChannel) else "texte"
            lines.append(f"  #{channel.name} ({kind}, id {channel.id})")
    return f"Salons de « {guild.name} » :\n" + "\n".join(lines)


@tool("list_members",
      "Liste les membres d'un serveur Discord (pseudos, rôles, bots). Pour « qui est sur le "
      "serveur », « qui a le rôle X », « combien on est ».",
      {"server": ("string", "Nom ou id du serveur (vide = serveur actuel)"),
       "role": ("string", "Ne garder que les membres qui ont ce rôle (optionnel)")})
async def list_members(ctx: ToolContext, server: str | None = None, role: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    members = resolve_role(guild, role).members if role else list(guild.members)
    if not members and not role and (guild.member_count or 0) > 1:
        return (f"Je ne vois pas la liste des membres de « {guild.name} » ({guild.member_count} membres) : "
                "active « Server Members Intent » dans le Developer Portal.")
    humans = sorted((m for m in members if not m.bot), key=lambda m: m.display_name.lower())
    bots = sorted((m for m in members if m.bot), key=lambda m: m.display_name.lower())

    def line(member) -> str:
        roles = [r.name for r in reversed(member.roles) if not r.is_default()][:3]
        name = member.display_name if member.display_name == member.name \
            else f"{member.display_name} (@{member.name})"
        return f"- {name}" + (f" — {', '.join(roles)}" if roles else "")

    header = f"Membres de « {guild.name} »" + (f" avec le rôle {role}" if role else "") + \
        f" : {len(humans)} personne(s), {len(bots)} bot(s)."
    lines = [line(m) for m in humans[:80]]
    if len(humans) > 80:
        lines.append(f"- … et {len(humans) - 80} autres")
    if bots:
        lines.append("Bots : " + ", ".join(b.display_name for b in bots[:20]))
    return "\n".join([header, *lines])


@tool("create_channel", "Crée un salon texte ou vocal.",
      {"name": ("string", "Nom du salon"),
       "server": ("string", "Serveur (vide = actuel)"),
       "kind": ("string", "« texte » ou « vocal »"),
       "category": ("string", "Catégorie (optionnel)")},
      required=("name",))
async def create_channel(ctx: ToolContext, name: str, server: str | None = None,
                         kind: str = "texte", category: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    parent = None
    if category:
        matches = [c for c in guild.categories if c.name.lower() == category.lower()]
        parent = matches[0] if matches else await guild.create_category(category)
    create = guild.create_voice_channel if kind.lower().startswith(("voc", "voice")) \
        else guild.create_text_channel
    channel = await create(name, category=parent, reason=f"Demandé par {ctx.author}")
    return f"Salon #{channel.name} créé dans « {guild.name} » (id {channel.id})."


@tool("delete_channel", "Supprime un salon.",
      {"channel": ("string", "Salon à supprimer"), "server": ("string", "Serveur (optionnel)")},
      required=("channel",), confirm="Supprimer le salon « {channel} »")
async def delete_channel(ctx: ToolContext, channel: str, server: str | None = None) -> str:
    target = await _channel(ctx, channel, server, messageable=False)
    name = target.name
    await target.delete(reason=f"Demandé par {ctx.author}")
    return f"Salon #{name} supprimé."


@tool("set_status", "Change le statut « Joue à … » de Rosalie.",
      {"text": ("string", "Texte du statut (vide = aucun)")})
async def set_status(ctx: ToolContext, text: str | None = None) -> str:
    await ctx.bot.change_presence(activity=discord.Game(text) if text else None)
    return f"Statut changé : {text}" if text else "Statut retiré."
