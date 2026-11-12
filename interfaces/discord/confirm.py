import io

import discord


class ConfirmView(discord.ui.View):
    """Boutons Confirmer / Annuler, cliquables uniquement par les owners."""

    def __init__(self, owner_ids: frozenset[int], timeout: float = 60,
                 labels: tuple[str, str] | None = None):
        super().__init__(timeout=timeout)
        self.__owner_ids = owner_ids
        self.value: bool | None = None
        if labels:
            buttons = [item for item in self.children if isinstance(item, discord.ui.Button)]
            for button, label in zip(buttons, labels):
                button.label = label

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


async def ask_code_confirmation(channel: discord.abc.Messageable, owner_ids: frozenset[int],
                                language: str, code: str, timeout: float = 300
                                ) -> tuple[bool, discord.Message]:
    """Montre le code à l'owner avec Exécuter / Annuler. Long code => fichier joint."""
    view = ConfirmView(owner_ids, timeout=timeout, labels=("Exécuter", "Annuler"))
    header = f"🧪 **Je voudrais exécuter ce code** ({language}) :"
    shown = code.replace("```", "`\u200b``")
    if len(shown) + len(header) + 20 <= 2000:
        message = await channel.send(f"{header}\n```{language}\n{shown}\n```", view=view)
    else:
        extension = "py" if language == "python" else "sh"
        file = discord.File(io.BytesIO(code.encode("utf-8")), filename=f"rosalie.{extension}")
        message = await channel.send(f"{header} (trop long, voir le fichier)", file=file, view=view)
    await view.wait()
    if view.value is None:
        await message.edit(view=None)
        await message.reply("⌛ Pas de réponse, je ne l'exécute pas.", mention_author=False)
    return bool(view.value), message
