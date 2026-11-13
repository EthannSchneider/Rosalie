import discord

from interfaces.discord.utils import conversation_key
from libs.config import SettingError
from libs.llm.ollama import OllamaError
from libs.log import Log
from interfaces.discord.utils import is_owner


async def _model_autocomplete(ctx: discord.AutocompleteContext) -> list[str]:
    try:
        models = await ctx.bot.rosalie.llm.list_models()
    except OllamaError:
        return []
    return [model for model in models if ctx.value.lower() in model.lower()][:25]


async def _persona_autocomplete(ctx: discord.AutocompleteContext) -> list[str]:
    names = [info.name for info in ctx.bot.rosalie.store.personas()]
    return [name for name in names if ctx.value.lower() in name][:25]


class Admin(discord.Cog):
    """Commandes /rosalie, réservées aux owners."""

    rosalie = discord.SlashCommandGroup("rosalie", "Contrôler Rosalie")

    def __init__(self, bot: discord.Bot):
        self.__bot = bot

    async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
        return await is_owner(self.__bot, ctx.author)

    async def cog_command_error(self, ctx: discord.ApplicationContext, error: Exception):
        if isinstance(error, discord.CheckFailure):
            await ctx.respond("Je n'obéis qu'à mon créateur.", ephemeral=True)
        else:
            raise error

    @rosalie.command(name="status", description="État du modèle, de la mémoire et de la conversation")
    async def status(self, ctx: discord.ApplicationContext):
        bot = self.__bot
        try:
            models = await bot.rosalie.llm.list_models()
            ollama = f"✅ joignable ({len(models)} modèles)"
            for model in {bot.rosalie.llm.model, bot.rosalie.config.embed_model}:
                if model not in models and f"{model}:latest" not in models:
                    ollama += f"\n⚠️ `{model}` non installé (`python bot.py pull {model}`)"
        except OllamaError as error:
            ollama = f"❌ {error}"
        channel_id = conversation_key(ctx)
        embed = discord.Embed(title="Rosalie", color=discord.Color.blurple())
        embed.add_field(name="Ollama", value=ollama, inline=False)
        embed.add_field(name="Modèle", value=f"`{bot.rosalie.llm.model}`")
        embed.add_field(name="Salon dédié", value="oui" if bot.rosalie.decider.is_dedicated(channel_id) else "non")
        embed.add_field(name="Historique ici", value=f"{len(bot.rosalie.memory.get(channel_id))} messages")
        embed.add_field(name="Souvenirs", value=str(bot.rosalie.long_term.count()))
        embed.add_field(name="Exemples d'entraînement", value=str(bot.rosalie.dataset.count()))
        initiative = bot.rosalie.config.initiative
        embed.add_field(name="Heartbeat", value="actif" if bot.rosalie.config.heartbeat else "coupé")
        embed.add_field(name="Initiative", value="oui" if initiative else "non")
        embed.add_field(name="Relances prévues", value=str(len(bot.rosalie.agenda.pending())))
        await ctx.respond(embed=embed, ephemeral=True)

    @rosalie.command(name="model", description="Changer le modèle Ollama utilisé")
    async def model(self, ctx: discord.ApplicationContext,
                    name: discord.Option(str, "Nom du modèle Ollama", autocomplete=_model_autocomplete)):
        try:
            self.__bot.rosalie.update_settings({"ollama_model": name})
        except SettingError as error:
            await ctx.respond(f"Refusé : {error}", ephemeral=True)
            return
        Log.command(f"{ctx.author.name} switched model to {name}")
        await ctx.respond(f"Modèle changé pour `{name}`.", ephemeral=True)

    @rosalie.command(name="here", description="Activer/désactiver ce salon : elle y répond à tous tes messages")
    async def here(self, ctx: discord.ApplicationContext):
        enabled = self.__bot.rosalie.settings.toggle_dedicated(conversation_key(ctx))
        await ctx.respond("Je répondrai à tous tes messages ici." if enabled
                          else "Ici, je ne répondrai que si tu m'appelles.", ephemeral=True)

    @rosalie.command(name="reset", description="Effacer l'historique de conversation de ce salon")
    async def reset(self, ctx: discord.ApplicationContext):
        self.__bot.rosalie.memory.clear(conversation_key(ctx))
        self.__bot.rosalie.decider.stop(conversation_key(ctx))
        await ctx.respond("Historique de ce salon effacé (mes souvenirs à long terme restent).",
                          ephemeral=True)

    @rosalie.command(name="stop", description="Mettre fin à la conversation en cours")
    async def stop(self, ctx: discord.ApplicationContext):
        self.__bot.rosalie.decider.stop(conversation_key(ctx))
        await ctx.respond("D'accord, je me tais jusqu'à ce que tu m'appelles.", ephemeral=True)

    @rosalie.command(name="agenda", description="Voir ses relances programmées")
    async def agenda(self, ctx: discord.ApplicationContext):
        followups = self.__bot.rosalie.agenda.pending()
        text = "\n".join(f.line() for f in followups) or "Aucune relance prévue."
        await ctx.respond(text[:2000], ephemeral=True)

    @rosalie.command(name="cancel", description="Annuler une relance programmée")
    async def cancel(self, ctx: discord.ApplicationContext,
                     followup_id: discord.Option(int, "Numéro de la relance (#id)")):
        done = self.__bot.rosalie.agenda.cancel(followup_id)
        await ctx.respond("Relance annulée." if done else "Cette relance n'existe pas.", ephemeral=True)

    @rosalie.command(name="initiative", description="Lui permettre (ou non) de t'écrire d'elle-même")
    async def initiative(self, ctx: discord.ApplicationContext,
                         enabled: discord.Option(bool, "Activer l'initiative")):
        self.__bot.rosalie.update_settings({"initiative": enabled})
        await ctx.respond("Je t'écrirai de moi-même quand j'en aurai envie." if enabled
                          else "D'accord, je ne t'écrirai plus de moi-même (les relances "
                               "programmées restent).", ephemeral=True)

    @rosalie.command(name="persona", description="Changer de personnalité (vide = recharger l'actuelle)")
    async def persona(self, ctx: discord.ApplicationContext,
                      name: discord.Option(str, "Nom de la personnalité", required=False,
                                           default=None, autocomplete=_persona_autocomplete)):
        rosalie = self.__bot.rosalie
        if name:
            try:
                rosalie.update_settings({"persona": name})
            except SettingError as error:
                await ctx.respond(f"Refusé : {error}", ephemeral=True)
                return
            Log.command(f"{ctx.author.name} switched persona to {name}")
        text = rosalie.persona.reload()
        await ctx.respond(f"Personnalité « {rosalie.persona.name} » chargée ({len(text)} caractères).",
                          ephemeral=True)

    @rosalie.command(name="memories", description="Voir ses souvenirs à long terme")
    async def memories(self, ctx: discord.ApplicationContext,
                       search: discord.Option(str, "Recherche (vide = les plus récents)",
                                              required=False, default=None)):
        long_term = self.__bot.rosalie.long_term
        memories = await long_term.search(search, limit=15, min_score=0.3) if search \
            else long_term.recent(15)
        text = "\n".join(memory.line() for memory in memories) or "Aucun souvenir."
        await ctx.respond(text[:2000], ephemeral=True)

    @rosalie.command(name="forget", description="Effacer un souvenir par son numéro")
    async def forget(self, ctx: discord.ApplicationContext,
                     memory_id: discord.Option(int, "Numéro du souvenir (#id)")):
        done = self.__bot.rosalie.long_term.forget(memory_id)
        await ctx.respond("Souvenir effacé." if done else "Ce souvenir n'existe pas.", ephemeral=True)


def setup(bot):
    bot.add_cog(Admin(bot))
