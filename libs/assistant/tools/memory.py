"""Mémoire à long terme : noter, chercher, oublier."""
from libs.assistant.tools.base import ToolContext, tool, _int


@tool("remember",
      "Note un souvenir durable dans ta mémoire à long terme : fait sur l'utilisateur, "
      "préférence, projet, date, décision, ou ce que tu as ressenti d'important. "
      "Une seule information par appel, formulée pour être comprise plus tard.",
      {"content": ("string", "L'information à retenir, en une phrase autonome"),
       "category": ("string", "personne | préférence | projet | événement | ressenti | autre"),
       "importance": ("integer", "1 à 5 ; 4-5 = à toujours garder en tête")},
      required=("content",))
async def remember(ctx: ToolContext, content: str, category: str = "autre", importance: int = 3) -> str:
    memory_id, updated = await ctx.rosalie.long_term.add(content, category, _int(importance, 3, 1, 5))
    return f"Souvenir #{memory_id} {'mis à jour' if updated else 'enregistré'}."


@tool("recall", "Cherche dans ta mémoire à long terme.",
      {"query": ("string", "Ce que tu cherches")}, required=("query",))
async def recall(ctx: ToolContext, query: str) -> str:
    memories = await ctx.rosalie.long_term.search(query, limit=8, min_score=0.35)
    return "\n".join(m.line() for m in memories) or "Aucun souvenir trouvé."


@tool("forget", "Oublie un souvenir (par son numéro #id).",
      {"memory_id": ("integer", "Numéro du souvenir")}, required=("memory_id",))
async def forget(ctx: ToolContext, memory_id: int) -> str:
    return "Souvenir oublié." if ctx.rosalie.long_term.forget(_int(memory_id, 0, 0, 10**9)) \
        else "Ce souvenir n'existe pas."
