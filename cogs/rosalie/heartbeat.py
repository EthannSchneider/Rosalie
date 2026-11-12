"""Heartbeat : le « cœur » de Rosalie bat à intervalle régulier, même quand personne ne parle.

À chaque battement :
  1. elle exécute les relances arrivées à échéance (plan_followup) — et décide encore,
     au moment venu, si elle parle ou se tait ;
  2. de temps en temps (INITIATIVE_EVERY), hors heures calmes, si la conversation est
     calme depuis un moment, elle a un « moment de réflexion » : elle peut t'écrire
     d'elle-même… ou, le plus souvent, choisir le silence.
"""
import time
import traceback

import discord
from discord.ext import tasks

from libs.conversation.initiative import (followup_note, parse_hours, reflection_note,
                                          reflection_skip_reason)
from libs.log import Log


class Heartbeat(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.__quiet = parse_hours(bot.config.quiet_hours)
        if bot.config.heartbeat:
            self.beat.change_interval(seconds=max(10, bot.config.heartbeat_interval))
            self.beat.start()

    def cog_unload(self):
        self.beat.cancel()

    @property
    def initiative_enabled(self) -> bool:
        value = self.bot.settings.initiative
        return self.bot.config.initiative if value is None else value

    @tasks.loop(seconds=60)
    async def beat(self):
        try:
            await self.__followups()
            await self.__reflect()
        except Exception as error:   # une erreur ne doit jamais arrêter le cœur
            Log.error(f"Heartbeat: {error}\n{traceback.format_exc()}")

    @beat.before_loop
    async def before_beat(self):
        await self.bot.wait_until_ready()
        # Pas de réflexion juste après un redémarrage
        if not self.bot.agenda.last_reflection:
            self.bot.agenda.mark_reflection()

    # --- relances programmées ---------------------------------------------------------
    async def __followups(self):
        chat = self.bot.get_cog("Chat")
        now = time.time()
        for followup in self.bot.agenda.pop_due(now):
            Log.info(f"Heartbeat: relance #{followup.id} ({followup.intention})")
            target = await self.__resolve(followup.channel_id, followup.user_id)
            if chat is None or target is None:
                Log.warning(f"Relance #{followup.id} abandonnée : salon ou personne introuvable")
                continue
            channel, user = target
            try:
                await chat.speak(channel, user, query=followup.intention,
                                 note=followup_note(followup.intention, followup.created, now))
            except Exception as error:
                Log.error(f"Relance #{followup.id} : {error}")

    # --- initiative -------------------------------------------------------------------
    async def __reflect(self):
        bot = self.bot
        home = bot.agenda.home
        chat = bot.get_cog("Chat")
        if home is None or chat is None:
            return
        channel_id, user_id = home
        now = time.time()
        entries = bot.memory.get(channel_id)
        last = entries[-1] if entries else None
        config = bot.config
        reason = reflection_skip_reason(
            now,
            enabled=self.initiative_enabled,
            quiet=self.__quiet,
            last_activity=last.timestamp if last else 0,
            last_reflection=bot.agenda.last_reflection,
            last_was_spontaneous=bool(last and last.is_bot and last.spontaneous),
            initiatives_today=bot.agenda.initiatives_since(now - 86400),
            every_minutes=config.initiative_every,
            min_silence_minutes=config.initiative_min_silence,
            max_per_day=config.initiative_max_per_day,
        )
        if reason:
            return
        bot.agenda.mark_reflection(now)
        if bot.agenda.pending(channel_id):
            return   # une relance est déjà prévue : elle n'a pas besoin d'en rajouter
        target = await self.__resolve(channel_id, user_id)
        if target is None:
            return
        channel, user = target
        Log.info("Heartbeat: moment de réflexion")
        reply = await chat.speak(channel, user, spontaneous=True,
                                 note=reflection_note(last.timestamp if last else 0, now,
                                                      user.display_name))
        if reply:
            bot.agenda.mark_initiative(now)

    async def __resolve(self, channel_id: int, user_id: int):
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        except discord.HTTPException:
            return None
        return channel, user


def setup(bot):
    bot.add_cog(Heartbeat(bot))
