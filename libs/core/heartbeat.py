"""Heartbeat : le « cœur » de Rosalie bat à intervalle régulier, même quand personne ne parle,
quelle que soit l'interface.

À chaque battement :
  1. elle exécute les relances arrivées à échéance (plan_followup) — et décide encore,
     au moment venu, si elle parle ou se tait ;
  2. de temps en temps (INITIATIVE_EVERY), hors heures calmes, si la conversation est
     calme depuis un moment, elle a un « moment de réflexion » dans la dernière conversation
     avec son créateur : elle peut lui écrire d'elle-même… ou, le plus souvent, se taire.
"""
from __future__ import annotations

import asyncio
import time
import traceback
from typing import TYPE_CHECKING

from libs.conversation.initiative import (followup_note, parse_hours, reflection_note,
                                          reflection_skip_reason)
from libs.log import Log

if TYPE_CHECKING:
    from libs.core.rosalie import Rosalie

STARTUP_DELAY = 10   # laisse aux interfaces le temps de se connecter


class Heartbeat:
    def __init__(self, rosalie: Rosalie):
        self.rosalie = rosalie

    @property
    def initiative_enabled(self) -> bool:
        return self.rosalie.config.initiative

    async def run(self):
        """Tourne tant que Rosalie vit ; HEARTBEAT et son intervalle se règlent à chaud."""
        await asyncio.sleep(STARTUP_DELAY)
        if not self.rosalie.agenda.last_reflection:   # pas de réflexion juste après un démarrage
            self.rosalie.agenda.mark_reflection()
        while True:
            config = self.rosalie.config
            if config.heartbeat:
                await self.beat()
            await asyncio.sleep(max(10, config.heartbeat_interval))

    async def beat(self):
        try:
            await self.followups()
            await self.reflect()
        except Exception as error:   # une erreur ne doit jamais arrêter le cœur
            Log.error(f"Heartbeat: {error}\n{traceback.format_exc()}")

    # --- relances programmées -------------------------------------------------------------
    async def followups(self):
        rosalie = self.rosalie
        now = time.time()
        for followup in rosalie.agenda.pop_due(now):
            Log.info(f"Heartbeat: relance #{followup.id} ({followup.intention})")
            target = await rosalie.resolve(followup.conversation, followup.person)
            if target is None:
                Log.warning(f"Relance #{followup.id} abandonnée : conversation ou personne "
                            f"introuvable ({followup.conversation}, interface lancée ?)")
                continue
            conversation, person = target
            try:
                await rosalie.speak(conversation, person, query=followup.intention,
                                    note=followup_note(followup.intention, followup.created, now))
            except Exception as error:
                Log.error(f"Relance #{followup.id} : {error}")

    # --- initiative -----------------------------------------------------------------------
    async def reflect(self):
        rosalie = self.rosalie
        home = rosalie.agenda.home
        if home is None:
            return
        conversation_key, person_key = home
        now = time.time()
        entries = rosalie.memory.get(conversation_key)
        last = entries[-1] if entries else None
        config = rosalie.config
        reason = reflection_skip_reason(
            now,
            enabled=self.initiative_enabled,
            quiet=parse_hours(config.quiet_hours),
            last_activity=last.timestamp if last else 0,
            last_reflection=rosalie.agenda.last_reflection,
            last_was_spontaneous=bool(last and last.is_bot and last.spontaneous),
            initiatives_today=rosalie.agenda.initiatives_since(now - 86400),
            every_minutes=config.initiative_every,
            min_silence_minutes=config.initiative_min_silence,
            max_per_day=config.initiative_max_per_day,
        )
        if reason:
            return
        rosalie.agenda.mark_reflection(now)
        if rosalie.agenda.pending(conversation_key):
            return   # une relance est déjà prévue : elle n'a pas besoin d'en rajouter
        target = await rosalie.resolve(conversation_key, person_key)
        if target is None:
            return
        conversation, person = target
        Log.info("Heartbeat: moment de réflexion")
        reply = await rosalie.speak(conversation, person, spontaneous=True,
                                    note=reflection_note(last.timestamp if last else 0, now,
                                                         person.display_name))
        if reply:
            rosalie.agenda.mark_initiative(now)
