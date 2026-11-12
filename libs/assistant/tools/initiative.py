"""Initiative : parler tout de suite, programmer ou annuler une relance."""
from libs.assistant.tools.base import ToolContext, tool, _int


@tool("say",
      "Envoie TOUT DE SUITE un message ici, dans la conversation en cours, puis continue ton "
      "travail : prévenir avant une tâche longue (« je regarde ça »), ou donner une première "
      "partie de réponse. Ta réponse finale sera envoyée après, en message séparé.",
      {"content": ("string", "Texte à envoyer maintenant")}, required=("content",))
async def say(ctx: ToolContext, content: str) -> str:
    await ctx.channel.send(content[:2000])
    return ("Message envoyé. Continue ce que tu faisais, puis donne la suite. "
            "Si tout est déjà dit, réponds [SILENCE].")


@tool("plan_followup",
      "Programme une relance : dans X minutes, tu reviendras de toi-même dans cette conversation "
      "pour faire ou dire quelque chose (rappel demandé, prendre des nouvelles, revenir avec "
      "une réponse plus réfléchie, relancer s'il ne répond pas). Au moment venu, tu décideras "
      "encore si c'est toujours utile.",
      {"minutes": ("integer", "Dans combien de minutes (1 à 10080)"),
       "intention": ("string", "Ce que tu comptes faire ou dire, assez précis pour t'en souvenir")},
      required=("minutes", "intention"))
async def plan_followup(ctx: ToolContext, minutes: int, intention: str) -> str:
    followup = ctx.bot.agenda.add(ctx.channel.id, ctx.author.id,
                                  _int(minutes, 30, 1, 10080) * 60, intention)
    return f"Relance programmée {followup.line()}."


@tool("cancel_followup", "Annule une relance programmée (par son numéro #id).",
      {"followup_id": ("integer", "Numéro de la relance")}, required=("followup_id",))
async def cancel_followup(ctx: ToolContext, followup_id: int) -> str:
    return "Relance annulée." if ctx.bot.agenda.cancel(_int(followup_id, 0, 0, 10**9)) \
        else "Cette relance n'existe pas."
