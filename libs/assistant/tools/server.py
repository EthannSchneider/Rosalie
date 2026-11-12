"""Serveurs : infos, salons, membres, rôles, invitations, fils, statut."""
import discord

from libs.assistant.resolver import ResolveError, resolve_guild, resolve_member, resolve_role
from libs.assistant.tools.base import ToolContext, tool, _channel, _int


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


def _date(value) -> str:
    return f"{value:%d.%m.%Y}" if value else "?"


@tool("server_info", "Infos sur un serveur : propriétaire, création, membres, salons, rôles, boosts.",
      {"server": ("string", "Nom ou id du serveur (vide = serveur actuel)")})
async def server_info(ctx: ToolContext, server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    humans = sum(1 for m in guild.members if not m.bot)
    return "\n".join([
        f"Serveur « {guild.name} » (id {guild.id})",
        f"- Propriétaire : {guild.owner.display_name if guild.owner else '?'}",
        f"- Créé le {_date(guild.created_at)}",
        f"- Membres : {guild.member_count} ({humans} personnes, {len(guild.members) - humans} bots)",
        f"- Salons : {len(guild.text_channels)} texte, {len(guild.voice_channels)} vocaux, "
        f"{len(guild.categories)} catégories",
        f"- Rôles : {len(guild.roles) - 1}, emojis : {len(guild.emojis)}",
        f"- Boosts : niveau {guild.premium_tier} ({guild.premium_subscription_count or 0} boosts)",
    ] + ([f"- Description : {guild.description}"] if guild.description else []))


@tool("member_info", "Infos sur un membre : surnom, rôles, arrivée sur le serveur, âge du compte.",
      {"member": ("string", "Pseudo, mention ou id"),
       "server": ("string", "Serveur (vide = actuel)")},
      required=("member",))
async def member_info(ctx: ToolContext, member: str, server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    target = await resolve_member(ctx.bot, member, guild)
    roles = [r.name for r in reversed(target.roles) if not r.is_default()]
    timed_out = getattr(target, "communication_disabled_until", None)
    return "\n".join(filter(None, [
        f"{target.display_name} (@{target.name}, id {target.id})" + (" — bot" if target.bot else ""),
        f"- Sur « {guild.name} » depuis le {_date(target.joined_at)}",
        f"- Compte créé le {_date(target.created_at)}",
        f"- Rôles : {', '.join(roles) if roles else 'aucun'}",
        f"- Exclu temporairement jusqu'au {timed_out:%d.%m %H:%M}" if timed_out else "",
    ]))


@tool("list_roles", "Liste les rôles d'un serveur avec leur nombre de membres.",
      {"server": ("string", "Serveur (vide = actuel)")})
async def list_roles(ctx: ToolContext, server: str | None = None) -> str:
    guild = resolve_guild(ctx.bot, server, ctx.guild)
    roles = [r for r in reversed(guild.roles) if not r.is_default()]
    lines = [f"- {r.name} : {len(r.members)} membre(s)" + (" (admin)" if r.permissions.administrator else "")
             for r in roles[:50]]
    return f"Rôles de « {guild.name} » :\n" + ("\n".join(lines) or "aucun rôle")


@tool("create_invite", "Crée un lien d'invitation vers un salon/serveur.",
      {"channel": ("string", "Salon (vide = ici)"),
       "hours": ("integer", "Validité en heures (0 = permanente, défaut 24)"),
       "max_uses": ("integer", "Nombre d'utilisations max (0 = illimité)")})
async def create_invite(ctx: ToolContext, channel: str | None = None, hours: int = 24,
                        max_uses: int = 0) -> str:
    target = await _channel(ctx, channel)
    if not hasattr(target, "create_invite"):
        raise ResolveError("on ne peut pas créer d'invitation ici (message privé ?)")
    invite = await target.create_invite(max_age=_int(hours, 24, 0, 168) * 3600,
                                        max_uses=_int(max_uses, 0, 0, 100),
                                        reason=f"Demandé par {ctx.author}")
    validity = f"{_int(hours, 24, 0, 168)} h" if _int(hours, 24, 0, 168) else "permanente"
    return f"Invitation créée : {invite.url} (validité {validity})."


@tool("create_thread", "Crée un fil de discussion dans un salon texte.",
      {"name": ("string", "Nom du fil"),
       "channel": ("string", "Salon (vide = ici)"),
       "message": ("string", "Premier message à poster dans le fil (optionnel)")},
      required=("name",))
async def create_thread(ctx: ToolContext, name: str, channel: str | None = None,
                        message: str | None = None) -> str:
    target = await _channel(ctx, channel)
    if not isinstance(target, discord.TextChannel):
        raise ResolveError("on ne peut créer un fil que dans un salon texte d'un serveur")
    thread = await target.create_thread(name=name[:100], type=discord.ChannelType.public_thread,
                                        reason=f"Demandé par {ctx.author}")
    if message:
        await thread.send(message[:2000])
    return f"Fil « {thread.name} » créé dans #{target.name} (id {thread.id})."
