import discord


class ConfirmView(discord.ui.View):
    """Boutons Confirmer / Annuler, cliquables uniquement par les owners."""

    def __init__(self, owner_ids: frozenset[int], timeout: float = 60):
        super().__init__(timeout=timeout)
        self.__owner_ids = owner_ids
        self.value: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self.__owner_ids:
            return True
        await interaction.response.send_message("Ce n'est pas à toi de confirmer.", ephemeral=True)
        return False

    async def __finish(self, interaction: discord.Interaction, value: bool):
        self.value = value
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.__finish(interaction, True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.__finish(interaction, False)


async def ask_confirmation(channel: discord.abc.Messageable, owner_ids: frozenset[int],
                           text: str) -> bool:
    view = ConfirmView(owner_ids)
    message = await channel.send(f"⚠️ {text} ?", view=view)
    await view.wait()
    if view.value is None:
        await message.edit(content=f"⌛ {text} — pas de réponse, annulé.", view=None)
    return bool(view.value)
