import discord

from libs.llm.ollama import OllamaError
from libs.log import Log
from libs.utils.permissions import is_owner


async def _model_autocomplete(ctx: discord.AutocompleteContext) -> list[str]:
    try:
        models = await ctx.bot.llm.list_models()
    except OllamaError:
        return []
    return [model for model in models if ctx.value.lower() in model.lower()][:25]


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
            models = await bot.llm.list_models()
            ollama = f"✅ joignable ({len(models)} modèles)"
            for model in {bot.llm.model, bot.config.embed_model}:
                if model not in models and f"{model}:latest" not in models:
                    ollama += f"\n⚠️ `{model}` non installé (`python bot.py pull {model}`)"
        except OllamaError as error:
            ollama = f"❌ {error}"
        channel_id = ctx.channel.id
        embed = discord.Embed(title="Rosalie", color=discord.Color.blurple())
        embed.add_field(name="Ollama", value=ollama, inline=False)
        embed.add_field(name="Modèle", value=f"`{bot.llm.model}`")
        embed.add_field(name="Salon dédié", value="oui" if bot.decider.is_dedicated(channel_id) else "non")
        embed.add_field(name="Historique ici", value=f"{len(bot.memory.get(channel_id))} messages")
        embed.add_field(name="Souvenirs", value=str(bot.long_term.count()))
        embed.add_field(name="Exemples d'entraînement", value=str(bot.dataset.count()))
        await ctx.respond(embed=embed, ephemeral=True)

    @rosalie.command(name="model", description="Changer le modèle Ollama utilisé")
    async def model(self, ctx: discord.ApplicationContext,
                    name: discord.Option(str, "Nom du modèle Ollama", autocomplete=_model_autocomplete)):
        self.__bot.llm.model = name
        self.__bot.settings.model = name
        Log.command(f"{ctx.author.name} switched model to {name}")
        await ctx.respond(f"Modèle changé pour `{name}`.", ephemeral=True)

    @rosalie.command(name="here", description="Activer/désactiver ce salon : elle y répond à tous tes messages")
    async def here(self, ctx: discord.ApplicationContext):
        enabled = self.__bot.settings.toggle_channel(ctx.channel.id)
        await ctx.respond("Je répondrai à tous tes messages ici." if enabled
                          else "Ici, je ne répondrai que si tu m'appelles.", ephemeral=True)

    @rosalie.command(name="reset", description="Effacer l'historique de conversation de ce salon")
    async def reset(self, ctx: discord.ApplicationContext):
        self.__bot.memory.clear(ctx.channel.id)
        self.__bot.decider.stop(ctx.channel.id)
        await ctx.respond("Historique de ce salon effacé (mes souvenirs à long terme restent).",
                          ephemeral=True)

    @rosalie.command(name="stop", description="Mettre fin à la conversation en cours")
    async def stop(self, ctx: discord.ApplicationContext):
        self.__bot.decider.stop(ctx.channel.id)
        await ctx.respond("D'accord, je me tais jusqu'à ce que tu m'appelles.", ephemeral=True)

    @rosalie.command(name="persona", description="Recharger le fichier de personnalité")
    async def persona(self, ctx: discord.ApplicationContext):
        text = self.__bot.persona.reload()
        await ctx.respond(f"Personnalité rechargée ({len(text)} caractères).", ephemeral=True)

    @rosalie.command(name="memories", description="Voir ses souvenirs à long terme")
    async def memories(self, ctx: discord.ApplicationContext,
                       search: discord.Option(str, "Recherche (vide = les plus récents)",
                                              required=False, default=None)):
        long_term = self.__bot.long_term
        memories = await long_term.search(search, limit=15, min_score=0.3) if search \
            else long_term.recent(15)
        text = "\n".join(memory.line() for memory in memories) or "Aucun souvenir."
        await ctx.respond(text[:2000], ephemeral=True)

    @rosalie.command(name="forget", description="Effacer un souvenir par son numéro")
    async def forget(self, ctx: discord.ApplicationContext,
                     memory_id: discord.Option(int, "Numéro du souvenir (#id)")):
        done = self.__bot.long_term.forget(memory_id)
        await ctx.respond("Souvenir effacé." if done else "Ce souvenir n'existe pas.", ephemeral=True)


def setup(bot):
    bot.add_cog(Admin(bot))
