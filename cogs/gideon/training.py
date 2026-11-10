import discord

from libs.conversation.prompt import build_messages, build_system_prompt
from libs.log import Log
from libs.utils.discord_utils import place_name
from libs.utils.permissions import is_owner


STAR_EMOJIS = ("⭐", "🌟")


class CorrectionModal(discord.ui.Modal):
    def __init__(self, cog: "Training", message: discord.Message, original: str):
        super().__init__(
            discord.ui.InputText(
                label="Réponse idéale de Gideon",
                style=discord.InputTextStyle.long,
                value=original[:4000],
                max_length=4000,
            ),
            title="Corriger la réponse",
        )
        self.__cog = cog
        self.__message = message

    async def callback(self, interaction: discord.Interaction):
        corrected = self.children[0].value.strip()
        saved = self.__cog.save_sample(self.__message, corrected, source="correction")
        if saved:
            self.__cog.bot.memory.replace_content(
                self.__message.channel.id, self.__message.id, corrected)
            try:
                await self.__message.edit(content=corrected[:2000])
            except discord.HTTPException:
                pass
        await interaction.response.send_message(
            "✅ Correction enregistrée pour l'entraînement." if saved
            else "❌ Pas enregistré : message introuvable, ou réponse liée à une action "
                 "(seules les réponses de discussion servent au fine-tuning).",
            ephemeral=True)


class Training(discord.Cog):
    """Collecte d'exemples pour le fine-tuning de la personnalité.

    - réagir ⭐ sur une réponse de Gideon  -> l'exemple est gardé tel quel
    - clic droit > Applications > « Corriger (Gideon) » -> tu réécris la réponse idéale
    """

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    def save_sample(self, message: discord.Message, reply: str, source: str) -> bool:
        context, entry = self.bot.memory.before(message.channel.id, message.id)
        if entry is None or not entry.is_bot or entry.acted or not context:
            return False
        # Prompt stable (sans souvenirs ni heure) pour que le modèle apprenne le style, pas les faits
        speaker = next((e.author_name for e in reversed(context) if not e.is_bot), None)
        system = build_system_prompt(self.bot.persona.text, self.bot.user.display_name,
                                     place_name(message.channel), speaker=speaker)
        messages = build_messages(system, context[-10:])
        self.bot.dataset.add(messages, reply, source=source, channel_id=message.channel.id)
        Log.info(f"Training sample saved ({source}), total: {self.bot.dataset.count()}")
        return True

    @discord.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) not in STAR_EMOJIS or payload.user_id not in self.bot.config.owner_ids:
            return
        channel = self.bot.get_channel(payload.channel_id) or await self.bot.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if message.author.id != self.bot.user.id:
            return
        _, entry = self.bot.memory.before(channel.id, message.id)
        if entry is None or not self.save_sample(message, entry.content, source="star"):
            Log.warning("Star on a message not found in history, sample not saved")

    @discord.message_command(name="Corriger (Gideon)")
    async def correct(self, ctx: discord.ApplicationContext, message: discord.Message):
        if not await is_owner(self.bot, ctx.author):
            await ctx.respond("Je n'obéis qu'à mon créateur.", ephemeral=True)
            return
        if message.author.id != self.bot.user.id:
            await ctx.respond("Ce n'est pas un message de Gideon.", ephemeral=True)
            return
        _, entry = self.bot.memory.before(message.channel.id, message.id)
        original = entry.content if entry else message.content
        await ctx.send_modal(CorrectionModal(self, message, original))


def setup(bot):
    bot.add_cog(Training(bot))
