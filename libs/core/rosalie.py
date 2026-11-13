"""Le cœur de Rosalie : ses services (cerveau, mémoires, agenda…) et sa façon de converser,
indépendamment de la messagerie. Les interfaces (interfaces/) lui transmettent les messages
reçus (`receive`) et elle leur demande d'envoyer, de montrer « écrit… », de confirmer…

  receive()  -> décide s'il faut répondre, attend que la personne ait fini d'écrire
  speak()    -> réfléchit (outils, code à faire confirmer), répond ou choisit le silence
  send()     -> envoie (découpé à la taille de la messagerie) et garde en mémoire
"""
from __future__ import annotations

import asyncio
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from libs import web
from libs.assistant.agent import run_agent
from libs.assistant.code_runner import (REFUSED_NOTE, environment_line, extract_code,
                                        result_note, run_code)
from libs.assistant.tools import ToolContext
from libs.browser import VirtualBrowser
from libs.config import Config, ConfigStore, legacy_owner_ids
from libs.config.schema import BY_KEY, FIELDS
from libs.conversation.agenda import Agenda
from libs.conversation.decider import ReplyDecider
from libs.conversation.initiative import SILENCE, is_silence, with_note
from libs.conversation.memory import ConversationMemory, Entry
from libs.conversation.prompt import build_messages, build_system_prompt, clean_reply
from libs.core.heartbeat import Heartbeat
from libs.core.interface import Interface
from libs.core.text import split_message
from libs.core.types import Conversation, Incoming, OutgoingFile, Person, Sent, split_key
from libs.dataset.store import DatasetStore
from libs.llm.ollama import OllamaClient, OllamaError
from libs.llm.persona import Persona
from libs.log import Log
from libs.memory.extractor import extract_memories
from libs.memory.long_term import LongTermMemory
from libs.settings import Settings
from libs.models import Accounts, main_database

ROSALIE_ID = "rosalie"   # auteur de ses propres messages dans l'historique
MUST_REPLY_NOTE = ("(Note système : on te parle directement, tu dois répondre. Pas de [SILENCE]. "
                   "Si tu ne peux pas faire ce qu'on te demande, explique pourquoi.)")
TYPING_EXTEND = 8.0      # un « écrit… » dure ~10 s (Discord)
CONFIG_CHECK_EVERY = 1.0  # secondes entre deux vérifications des réglages (autre processus)


@dataclass
class _Pending:
    """Réponse en attente : elle laisse la personne finir d'écrire avant de répondre."""
    incoming: Incoming
    deadline: float
    limit: float
    direct: bool = False
    task: asyncio.Task | None = None


class Rosalie:
    def __init__(self, config: Config, store: ConfigStore):
        self.store = store                 # réglages modifiables à chaud (CLI, interface web)
        self.__config = config
        self.__revision = store.revision
        self.__checked = time.monotonic()
        self.settings = Settings(config.storage_dir / "settings.json")
        # Comptes : qui est qui (rôles, identifiant Discord lié), pour toutes les interfaces
        self.accounts = Accounts(main_database(config.storage_dir))
        self.__warned_legacy = False
        self.persona = Persona(lambda: self.config.persona, store)
        self.llm = OllamaClient(
            base_url=config.ollama_url,
            model=config.ollama_model,
            keep_alive=config.ollama_keep_alive,
            options={"num_ctx": config.num_ctx, "temperature": config.temperature},
        )
        self.agenda = Agenda(config.storage_dir / "agenda.json")
        self.memory = ConversationMemory(config.storage_dir / "memory", config.history_size)
        self.long_term = LongTermMemory(config.storage_dir / "long_term.sqlite3", self.llm,
                                        config.embed_model)
        self.dataset = DatasetStore(config.storage_dir / "dataset" / "samples.jsonl")
        self.decider = ReplyDecider(lambda: self.config, self.llm, self.settings)
        self.browser = VirtualBrowser(web.USER_AGENT)   # ne démarre Chromium qu'au besoin
        self.heartbeat = Heartbeat(self)
        self.interfaces: dict[str, Interface] = {}

        self.__locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.__pending: dict[str, _Pending] = {}
        self.__background: set[asyncio.Task] = set()

    # --- réglages -----------------------------------------------------------------------------
    @property
    def config(self) -> Config:
        """Réglages actuels. Une modification (CLI, interface web, /rosalie …) est prise en compte
        au plus tard une seconde après, sans redémarrer."""
        now = time.monotonic()
        if now - self.__checked >= CONFIG_CHECK_EVERY:
            self.__checked = now
            self.store.refresh()
        if self.store.revision != self.__revision:
            self.__revision = self.store.revision
            self.__apply(Config.load(self.store, self.__config.storage_dir))
        return self.__config

    def discord_permissions(self, discord_id: int) -> frozenset[str]:
        """Ce que cette personne Discord peut lui faire faire : les permissions du compte lié
        à son identifiant (anciens OWNER_IDS : tout, tant qu'aucun owner n'est lié)."""
        user = self.accounts.find_by_discord(discord_id)
        if user is not None:
            return user.permissions
        if discord_id in self.discord_owners():   # transition : ancien OWNER_IDS
            from libs.models.role import PERMISSIONS
            return frozenset(PERMISSIONS)
        return frozenset({"web"}) if self.config.guest_web else frozenset()   # inconnu : invité

    def discord_owners(self) -> frozenset[int]:
        """Les identifiants Discord à qui elle obéit : comptes liés dont le rôle a au moins une « act.* ».
        Tant qu'aucun n'est lié, les anciens OWNER_IDS restent valables (transition)."""
        linked = self.accounts.discord_owner_ids()
        if linked:
            return linked
        legacy = legacy_owner_ids(self.store)
        if legacy and not self.__warned_legacy:
            self.__warned_legacy = True
            Log.warning("Discord : les anciens OWNER_IDS sont encore utilisés. Lie ton identifiant "
                        "Discord à ton compte (site web > Mon compte, ou python bot.py users discord "
                        "<nom> <id>) : ils seront alors ignorés.")
        return legacy

    def update_settings(self, changes: dict[str, Any]) -> list[str]:
        """Modifie des réglages (validés, enregistrés). Retourne les clés changées."""
        changed = self.store.update(changes)
        _ = self.config   # appliqué tout de suite
        return changed

    def __apply(self, new: Config):
        old, self.__config = self.__config, new
        self.llm.base_url = new.ollama_url.rstrip("/")
        self.llm.model = new.ollama_model
        self.llm.keep_alive = new.ollama_keep_alive
        self.llm.options = {**self.llm.options, "num_ctx": new.num_ctx,
                            "temperature": new.temperature}
        changed = [field.key for field in FIELDS if getattr(old, field.key) != getattr(new, field.key)]
        if changed:
            Log.info(f"Réglages mis à jour : {', '.join(changed)}")
        later = [key for key in changed if BY_KEY[key].restart]
        if later:
            Log.warning(f"Pris en compte au prochain démarrage : {', '.join(later)}")

    @property
    def name(self) -> str:
        return self.config.names[0].capitalize() if self.config.names else "Rosalie"

    # --- cycle de vie ---------------------------------------------------------------------
    def add_interface(self, interface: Interface):
        self.interfaces[interface.name] = interface

    async def run(self):
        """Lance toutes les interfaces + le heartbeat, jusqu'à ce qu'elles s'arrêtent."""
        if not self.interfaces:
            Log.error("Aucune interface à lancer (INTERFACES).")
            return
        Log.info(f"{self.name} démarre : {', '.join(self.interfaces)} "
                 f"(modèle : {self.llm.model}, souvenirs : {self.long_term.count()})")
        heartbeat = asyncio.create_task(self.heartbeat.run())
        try:
            await asyncio.gather(*(self.__run_interface(i) for i in list(self.interfaces.values())))
        finally:
            heartbeat.cancel()
            await self.close()

    async def __run_interface(self, interface: Interface):
        try:
            await interface.start()
        except Exception as error:
            Log.error(f"Interface {interface.name} arrêtée : {error}\n{traceback.format_exc()}")
        finally:
            self.interfaces.pop(interface.name, None)

    async def shutdown(self):
        """Arrête toutes les interfaces (ex : /quit dans le terminal)."""
        for interface in list(self.interfaces.values()):
            await interface.stop()

    async def close(self):
        for pending in self.__pending.values():
            if pending.task:
                pending.task.cancel()
        await self.llm.close()
        await self.browser.close()
        self.long_term.close()
        self.accounts.close()
        self.store.close()

    # --- recevoir ---------------------------------------------------------------------------
    async def receive(self, incoming: Incoming):
        """Point d'entrée des interfaces pour chaque message reçu (hors messages de bots)."""
        conversation, author = incoming.conversation, incoming.author
        Log.message(self.where(conversation), incoming.text, author.name)
        decision = await self.decider.decide(incoming, self.memory.get(conversation.key))

        if decision.record:
            self.memory.add(conversation.key, Entry(
                author_id=author.key, author_name=author.display_name, content=incoming.text,
                is_bot=False, message_id=incoming.message_id))
            if author.is_owner:
                self.agenda.set_home(conversation.key, author.key)
        if not decision:
            Log.info(f"Not replying to {author.name} ({decision.reason})")
            return
        Log.info(f"Will reply to {author.name} ({decision.reason})")
        self.__schedule(incoming, decision.direct)

    def typing_from(self, conversation: str, person: str):
        """La personne écrit la suite : elle attend encore un peu avant de répondre."""
        pending = self.__pending.get(conversation)
        if pending and person == pending.incoming.author.key:
            pending.deadline = min(pending.limit, time.monotonic() + TYPING_EXTEND)

    def __schedule(self, incoming: Incoming, direct: bool):
        config = self.config
        now = time.monotonic()
        key = incoming.conversation.key
        pending = self.__pending.get(key)
        if pending:   # elle attendait déjà : on répondra à l'ensemble, après ce message
            pending.incoming = incoming
            pending.direct = pending.direct or direct
            pending.deadline = min(pending.limit, now + config.reply_delay)
            return
        delay = 0 if incoming.conversation.interface == "terminal" else config.reply_delay
        pending = _Pending(incoming, now + delay, now + config.reply_max_wait, direct)
        self.__pending[key] = pending
        pending.task = asyncio.create_task(self.__wait_then_reply(pending))

    async def __wait_then_reply(self, pending: _Pending):
        key = pending.incoming.conversation.key
        try:
            while (remaining := pending.deadline - time.monotonic()) > 0:
                await asyncio.sleep(remaining)
        finally:
            self.__pending.pop(key, None)
        await self.reply(pending.incoming, pending.direct)

    async def reply(self, incoming: Incoming, direct: bool = False) -> str | None:
        conversation, author = incoming.conversation, incoming.author
        try:
            reply = await self.speak(conversation, author, reply_to=incoming.message_id,
                                     query=incoming.text, must_reply=direct)
        except OllamaError as error:
            Log.error(f"Ollama error: {error}")
            text = "Je n'arrive pas à joindre mon cerveau… Ollama est lancé ?" \
                if "unreachable" in str(error) else f"⚠️ Problème avec mon cerveau (Ollama) : {error}"
            await self.send(conversation, text, reply_to=incoming.message_id)
            return None
        except Exception as error:
            Log.error(f"{error}\n{traceback.format_exc()}")
            await self.send(conversation, f"Oups, j'ai planté : `{error}`", reply_to=incoming.message_id)
            return None
        self.decider.mark_active(conversation.key, author.key)

        if reply is not None and author.can("act.memory"):   # prise de notes, sans bloquer
            task = asyncio.create_task(extract_memories(
                self.llm, self.config.decider_model, self.long_term,
                author.display_name, incoming.text, reply))
            self.__background.add(task)
            task.add_done_callback(self.__background.discard)
        return reply

    # --- parler -------------------------------------------------------------------------------
    async def speak(self, conversation: Conversation, person: Person, *, reply_to: Any = None,
                    note: str | None = None, query: str | None = None, spontaneous: bool = False,
                    must_reply: bool = False) -> str | None:
        """Fait réfléchir/agir Rosalie dans cette conversation et envoie sa réponse.
        Retourne le texte envoyé, ou None si elle a choisi le silence.
        `note` : consigne système ajoutée en fin de conversation (relance, réflexion).
        Sans `reply_to` (initiative), pas de « écrit… » si elle finit par se taire."""
        async with self.__locks[conversation.key]:
            reply, trace, errors = await self.__think(conversation, person, query, note,
                                                      typing=reply_to is not None,
                                                      must_reply=must_reply)
            if errors:   # une erreur est toujours dite, même si elle comptait se taire
                reply = "\n\n".join(filter(None, [reply, errors_footer(errors)]))

            if reply is None:
                Log.info(f"{self.name} choisit de ne rien dire ({self.where(conversation)})")
                if trace:   # elle a agi sans rien dire : on le garde en mémoire, et un ✅
                    self.memory.add(conversation.key, Entry(
                        author_id=ROSALIE_ID, author_name=self.name, content="", is_bot=True,
                        acted=True, tool_messages=trace, spontaneous=spontaneous))
                    if reply_to is not None:
                        await self.interface_of(conversation).react(conversation, reply_to, "✅")
                return None

            quote = reply_to if not conversation.private \
                and not self.decider.is_dedicated(conversation.key) else None
            sent = await self.send(conversation, reply, reply_to=quote)
            self.memory.add(conversation.key, Entry(
                author_id=ROSALIE_ID, author_name=self.name, content=reply, is_bot=True,
                message_id=sent.id, acted=bool(trace), tool_messages=trace,
                spontaneous=spontaneous))
            return reply

    async def __think(self, conversation: Conversation, person: Person, query: str | None,
                      note: str | None, typing: bool, must_reply: bool = False
                      ) -> tuple[str | None, list[dict], list[str]]:
        """Réflexion + outils ; si elle écrit un bloc run-python/run-bash : confirmation par
        l'owner, exécution, et elle reprend avec la sortie (jusqu'à CODE_MAX_RUNS fois)."""
        config = self.config
        interface = self.interface_of(conversation)
        messages = build_messages(await self.system_prompt(conversation, person, query),
                                  self.memory.get(conversation.key), tools=True)
        if note:
            with_note(messages, note)
        ctx = ToolContext(rosalie=self, conversation=conversation, person=person)
        trace: list[dict] = []
        errors: list[str] = []
        runs = 0
        insisted = False

        async def progress(text: str):
            """Point d'étape pendant une longue suite d'actions : envoyé tout de suite."""
            text = clean_reply(text, self.name)
            if text and not is_silence(text):
                await self.send(conversation, text, record=True)

        while True:
            async with interface.typing(conversation) if typing else _nothing():
                result = await run_agent(self.llm, messages, ctx, max_steps=config.max_tool_steps,
                                         acted=runs > 0, progress_every=config.progress_every,
                                         on_progress=progress)
            if result.actions:
                Log.info("Actions: " + " | ".join(result.actions))
            trace += result.trace
            errors += result.errors
            reply = clean_reply(result.text, self.name)
            block = extract_code(reply) if person.can("act.code") and config.code_exec else None
            if block is None or runs >= config.code_max_runs:
                if not is_silence(reply):
                    return reply, trace, errors
                if not must_reply:
                    return None, trace, errors
                if insisted:   # elle n'arrive pas à répondre : on le dit plutôt que se taire
                    Log.warning("Réponse vide malgré une question directe")
                    return "Désolée, je n'ai pas réussi à formuler de réponse… Tu peux reformuler ?", \
                        trace, errors
                insisted = True
                Log.info("Silence refusé : on lui parle directement, on lui redemande")
                messages += [{"role": "assistant", "content": reply or SILENCE},
                             {"role": "user", "content": MUST_REPLY_NOTE}]
                continue

            runs += 1
            if block.before:
                await self.send(conversation, block.before)
            confirmed, shown = await interface.confirm(
                conversation, "Je voudrais exécuter ce code", code=block.code, language=block.language)
            if not confirmed:
                Log.info("Code refusé par l'owner")
                trace += [{"role": "assistant", "content": reply},
                          {"role": "user", "content": REFUSED_NOTE}]
                return "D'accord, je ne l'exécute pas.", trace, errors

            Log.command(f"run {block.language} ({len(block.code)} caractères)")
            async with interface.typing(conversation):
                outcome = await run_code(block, config.storage_dir / "workspace", config.code_timeout)
            Log.info(f"Code : {outcome.summary()}")
            output = outcome.output.replace("```", "`​``")[:1800] or "(aucune sortie)"
            await self.send(conversation, f"{outcome.summary()}\n```\n{output}\n```",
                            reply_to=shown.id if shown else None)

            note_message = {"role": "user", "content": result_note(outcome)}
            messages += [{"role": "assistant", "content": reply}, note_message]
            trace += [{"role": "assistant", "content": reply}, note_message]

    async def system_prompt(self, conversation: Conversation, person: Person,
                            query: str | None = None) -> str:
        """Prompt système : persona + contexte + souvenirs (importants + liés au message).
        Pour un non-owner : aucun souvenir, aucune action. Pour un owner : seulement ce que ses
        permissions autorisent (souvenirs : act.memory, code : act.code, relances : act.followups)."""
        interface = self.interface_of(conversation)
        if not person.is_owner:
            return build_system_prompt(self.persona.text, self.name, conversation.place,
                                       speaker=person.display_name, guest=True,
                                       web=self.config.web_access and person.can("web"),
                                       via=interface.label)
        memories, related = {}, []
        if person.can("act.memory"):
            memories = {m.id: m for m in self.long_term.core()}
            related = await self.long_term.search(query, limit=5) if query else []
        for memory in related:
            memories.setdefault(memory.id, memory)
        context = [line for i in self.interfaces.values() for line in i.prompt_context()]
        return build_system_prompt(
            self.persona.text, self.name, conversation.place,
            speaker=person.display_name,
            context=context,
            memories=[memory.line() for memory in memories.values()],
            nothing_related=person.can("act.memory") and bool(query) and not related,
            followups=[f.line() for f in self.agenda.pending(conversation.key)]
            if person.can("act.followups") else [],
            code_env=environment_line(self.config.storage_dir / "workspace")
            if self.config.code_exec and person.can("act.code") else None,
            via=interface.label,
        )

    # --- envoyer ------------------------------------------------------------------------------
    async def send(self, conversation: Conversation, text: str | None, *,
                   files: list[OutgoingFile] = (), reply_to: Any = None,
                   record: bool = False, record_as: str | None = None) -> Sent:
        """Envoie via l'interface de la conversation, découpé à sa taille max.
        record=True : l'ajoute à l'historique de cette conversation (envoi par un outil)."""
        interface = self.interface_of(conversation)
        chunks = split_message(text or "", interface.message_limit) or [None]
        sent = Sent()
        for index, chunk in enumerate(chunks):
            last = index == len(chunks) - 1
            sent = await interface.send(conversation, chunk, files=files if last else (),
                                        reply_to=reply_to if index == 0 else None)
        if text:
            Log.message(self.where(conversation), text, self.name)
        if record:
            self.remember_sent(conversation.key, record_as or text or "", sent.id)
        return sent

    def remember_sent(self, conversation: str, content: str, message_id: Any = None,
                      current: str | None = None):
        """Un message envoyé par un outil entre dans l'historique de sa conversation : si la
        personne répond, elle sait ce qu'elle lui a écrit. (Pas pour la conversation courante :
        la réponse finale y est déjà enregistrée.)"""
        if conversation == current:
            return
        self.memory.add(conversation, Entry(
            author_id=ROSALIE_ID, author_name=self.name, content=content,
            is_bot=True, message_id=message_id, acted=True))

    # --- retrouver ----------------------------------------------------------------------------
    def interface_of(self, conversation: Conversation) -> Interface:
        interface = self.interfaces.get(conversation.interface)
        if interface is None:
            raise RuntimeError(f"interface {conversation.interface} non lancée")
        return interface

    async def resolve(self, conversation: str, person: str) -> tuple[Conversation, Person] | None:
        """Clés « interface:id » -> objets (heartbeat, relances). None si introuvable."""
        interface = self.interfaces.get(split_key(conversation)[0])
        if interface is None or split_key(person)[0] != interface.name:
            return None
        found = await interface.conversation(split_key(conversation)[1])
        who = await interface.person(split_key(person)[1])
        return (found, who) if found and who else None

    def where(self, conversation: Conversation) -> str:
        interface = self.interfaces.get(conversation.interface)
        return f"{interface.label if interface else conversation.interface} · {conversation.place}"


def errors_footer(errors: list[str]) -> str:
    unique = list(dict.fromkeys(errors))
    title = "⚠️ Une action a échoué :" if len(unique) == 1 else f"⚠️ {len(unique)} actions ont échoué :"
    lines = []
    for error in unique[:5]:
        name, _, detail = error.partition(" : ")
        lines.append(f"- `{name}` : {detail}")
    if len(unique) > 5:
        lines.append(f"- … et {len(unique) - 5} autre(s)")
    return "\n".join([title, *lines])


class _nothing:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False
