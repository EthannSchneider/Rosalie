"""Interface terminal : discuter avec Rosalie dans la console, sans Discord.

  python bot.py chat               seulement le terminal
  INTERFACES="discord,terminal"    les deux à la fois (elle reste la même : mémoire, souvenirs…)

La personne au clavier est son créateur (c'est ta machine) : tous les outils sont permis,
les confirmations se font au clavier (o/n). /quit pour quitter.
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys
from typing import Any

from libs.core.interface import Interface
from libs.core.types import Conversation, Incoming, OutgoingFile, Person, Sent

CONVERSATION_ID = "local"
FILES_DIR = "terminal_files"   # fichiers reçus (images…) dans storages/


class TerminalInterface(Interface):
    name = "terminal"
    label = "Terminal"
    message_limit = 100_000

    def __init__(self, rosalie, stdin=None, stdout=None):
        super().__init__(rosalie)
        self.__stdin = stdin or sys.stdin
        self.__stdout = stdout or sys.stdout
        self.__user = getpass.getuser()
        self.__running = False
        self.__answer: asyncio.Future | None = None   # confirmation en attente d'une réponse
        self.__sent = 0

    # --- identité ---------------------------------------------------------------------------
    @property
    def me(self) -> Person:
        return Person(self.name, self.__user, self.__user, self.__user.capitalize(), is_owner=True)

    @property
    def here(self) -> Conversation:
        return Conversation(self.name, CONVERSATION_ID, f"en tête-à-tête avec {self.__user}",
                            private=True)

    # --- cycle de vie -----------------------------------------------------------------------
    async def start(self):
        os.environ["LOG_QUIET"] = "1"   # les logs vont dans log.txt, pas au milieu de la discussion
        self.__running = True
        self.__print(f"💬 {self.rosalie.name} t'écoute dans le terminal (/quit pour quitter).")
        loop = asyncio.get_running_loop()
        while self.__running:
            line = await loop.run_in_executor(None, self.__stdin.readline)
            if not line:   # fin de l'entrée (Ctrl+D)
                break
            text = line.strip()
            if not text:
                continue
            if self.__answer is not None and not self.__answer.done():   # réponse à une confirmation
                self.__answer.set_result(text)
                continue
            if text in ("/quit", "/exit"):
                break
            asyncio.create_task(self.rosalie.receive(Incoming(self.here, self.me, text)))
        self.__running = False
        await self.rosalie.shutdown()

    async def stop(self):
        self.__running = False

    # --- envoyer ----------------------------------------------------------------------------
    async def send(self, conversation: Conversation, text: str | None = None, *,
                   files: list[OutgoingFile] = (), reply_to: Any = None) -> Sent:
        self.__sent += 1
        if text:
            self.__print(f"\n🌸 {self.rosalie.name} : {text}\n")
        for file in files:
            folder = self.rosalie.config.storage_dir / FILES_DIR
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{self.__sent}-{file.filename}"
            path.write_bytes(file.data)
            self.__print(f"📎 fichier enregistré : {path}")
        return Sent(self.__sent, conversation)

    async def confirm(self, conversation: Conversation, text: str, *, code: str | None = None,
                      language: str | None = None) -> tuple[bool, Sent | None]:
        shown = f"\n⚠️  {text}" + (f" ({language}) :\n{code}\n" if code else " ?")
        self.__print(shown + "\nConfirmer ? [o/N] ")
        self.__answer = asyncio.get_running_loop().create_future()
        try:
            answer = await asyncio.wait_for(self.__answer, timeout=300)
        except asyncio.TimeoutError:
            self.__print("⌛ Pas de réponse, annulé.")
            return False, None
        confirmed = answer.strip().lower() in ("o", "oui", "y", "yes")
        self.__print("✅ Confirmé." if confirmed else "❌ Annulé.")
        self.__sent += 1
        return confirmed, Sent(self.__sent, conversation)

    # --- retrouver --------------------------------------------------------------------------
    async def conversation(self, conversation_id: str) -> Conversation | None:
        return self.here if conversation_id == CONVERSATION_ID else None

    async def person(self, person_id: str) -> Person | None:
        return self.me if person_id == self.__user else None

    def __print(self, text: str):
        self.__stdout.write(text + ("" if text.endswith(" ") else "\n"))
        self.__stdout.flush()
