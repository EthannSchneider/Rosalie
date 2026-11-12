"""Petits outils de texte communs à toutes les interfaces."""


def split_message(text: str, limit: int = 2000) -> list[str]:
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
