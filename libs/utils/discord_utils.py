import discord


DISCORD_LIMIT = 2000


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """Découpe un texte en morceaux <= limit, de préférence sur les retours à la ligne."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


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
