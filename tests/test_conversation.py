import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from libs.config import Config
from libs.conversation.decider import ReplyDecider
from libs.conversation.memory import ConversationMemory, Entry
from libs.conversation.prompt import build_messages, build_system_prompt, clean_reply
from libs.core.text import split_message
from libs.core.types import Conversation, Incoming, Person
from libs.settings import Settings

BOT_ID = 1
ME = 42
OTHER = 99


def make_config(**overrides) -> Config:
    with mock.patch.dict("os.environ", {}, clear=True):
        config = Config.from_env()
    values = {**config.__dict__, "use_llm_decider": False, **overrides}
    return Config(**values)


def make_message(content, author_id=ME, mentioned=False, mentions_other=False, private=False,
                 reply_to_bot=None, owners=frozenset({ME})):
    """Ce qu'une interface transmet au cœur (signaux déjà calculés)."""
    return Incoming(
        conversation=Conversation("discord", 10, "salon #test", private=private),
        author=Person("discord", author_id, "ethann", "Ethann", is_owner=author_id in owners),
        text=content, mentioned=mentioned, mentions_other=mentions_other,
        reply_to_bot=reply_to_bot)


class FakeSettings:
    dedicated: set = set()


class DeciderTest(unittest.TestCase):
    def setUp(self):
        self.bot_user = SimpleNamespace(id=BOT_ID, display_name="Rosalie")

    def decide(self, message, config=None, decider=None):
        decider = decider or ReplyDecider(config or make_config(), None, FakeSettings())
        return asyncio.run(decider.decide(message, []))

    def test_name_triggers_reply(self):
        self.assertTrue(self.decide(make_message("hey Rosalie tu fais quoi")))

    def test_name_inside_word_does_not_trigger(self):
        self.assertFalse(self.decide(make_message("rosaliesoft est cool")))

    def test_mention_triggers_reply(self):
        self.assertTrue(self.decide(make_message("salut", mentioned=True)))

    def test_random_message_ignored(self):
        self.assertFalse(self.decide(make_message("quelqu'un joue ce soir ?")))

    def test_ignore_prefix(self):
        self.assertFalse(self.decide(make_message("// rosalie chut")))

    def test_only_owner_when_public_replies_off(self):
        config = make_config(public_replies=False)
        self.assertFalse(self.decide(make_message("rosalie ?", author_id=OTHER), config))
        self.assertTrue(self.decide(make_message("rosalie ?", author_id=ME), config))
        self.assertFalse(self.decide(make_message("rosalie ?", owners=frozenset()), config))

    def test_guest_can_chat_with_cooldown(self):
        decider = ReplyDecider(make_config(public_cooldown=60), None, FakeSettings())
        self.assertFalse(self.decide(make_message("salut", author_id=OTHER), decider=decider))
        self.assertTrue(self.decide(make_message("rosalie ?", author_id=OTHER), decider=decider))
        self.assertFalse(self.decide(make_message("rosalie ??", author_id=OTHER), decider=decider))
        self.assertTrue(self.decide(make_message("rosalie ?", author_id=ME), decider=decider))

    def test_guest_prompt_has_no_memories_nor_actions(self):
        prompt = build_system_prompt("PERSONA", "Rosalie", "DM", speaker="Sachiko",
                                     memories=["Ethann habite à Lausanne"], guest=True)
        self.assertIn("PAS ton créateur", prompt)
        self.assertNotIn("Lausanne", prompt)
        self.assertNotIn("send_message", prompt)

    def test_dedicated_channel(self):
        config = make_config(channel_ids=frozenset({10}))
        self.assertTrue(self.decide(make_message("tu peux m'aider ?"), config))
        self.assertFalse(self.decide(make_message("tu viens ?", mentions_other=True), config))

    def test_active_conversation(self):
        decider = ReplyDecider(make_config(), None, FakeSettings())
        self.assertFalse(self.decide(make_message("et ensuite ?"), decider=decider))
        decider.mark_active("discord:10", f"discord:{ME}")
        self.assertTrue(self.decide(make_message("et ensuite ?"), decider=decider))
        decider.stop("discord:10")
        self.assertFalse(self.decide(make_message("et ensuite ?"), decider=decider))


class PromptTest(unittest.TestCase):
    def test_build_messages_merges_consecutive_roles(self):
        entries = [
            Entry(ME, "Ethann", "salut", False),
            Entry(ME, "Ethann", "t'es là ?", False),
            Entry(BOT_ID, "Rosalie", "Oui !", True),
        ]
        messages = build_messages("SYS", entries)
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant"])
        self.assertEqual(messages[1]["content"], "salut\nt'es là ?")

    def test_build_messages_replays_tool_calls(self):
        call = {"role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "send_dm",
                                             "arguments": {"user": "Sachiko", "content": "Coucou"}}}]}
        entries = [
            Entry(ME, "Ethann", "envoie coucou à Sachiko", False),
            Entry(BOT_ID, "Rosalie", "C'est envoyé !", True, acted=True,
                  tool_messages=[call, {"role": "tool", "content": "ok", "tool_name": "send_dm"}]),
            Entry(ME, "Ethann", "tu lui as dit quoi ?", False),
        ]
        roles = [m["role"] for m in build_messages("SYS", entries, tools=True)]
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "assistant", "user"])
        # Sans tools (fine-tuning) : uniquement le texte
        roles = [m["role"] for m in build_messages("SYS", entries)]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])

    def test_system_prompt_contains_memories(self):
        prompt = build_system_prompt("PERSONA", "Rosalie", "DM", context=["Serveurs : Le Bunker"],
                                     memories=["#1 anniversaire le 14 mars"])
        self.assertIn("Le Bunker", prompt)
        self.assertIn("#1 anniversaire le 14 mars", prompt)

    def test_clean_reply(self):
        self.assertEqual(clean_reply("Rosalie: Salut.", "Rosalie"), "Salut.")
        self.assertEqual(clean_reply("<think>\nhmm\n</think>\n\nSalut !", "Rosalie"), "Salut !")


class MemoryTest(unittest.TestCase):
    def test_persist_and_trim(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ConversationMemory(Path(directory), max_size=2)
            for index in range(3):
                memory.add("discord:5", Entry(ME, "Ethann", f"m{index}", False, message_id=index))
            reloaded = ConversationMemory(Path(directory), max_size=2)
            self.assertEqual([e.content for e in reloaded.get("discord:5")], ["m1", "m2"])
            context, entry = reloaded.before("discord:5", 2)
            self.assertEqual(entry.content, "m2")
            self.assertEqual(len(context), 1)


class SplitTest(unittest.TestCase):
    def test_split(self):
        text = ("a" * 1500 + "\n") * 3
        chunks = split_message(text)
        self.assertTrue(all(len(chunk) <= 2000 for chunk in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), "a" * 4500)


class DirectDecisionTest(unittest.TestCase):
    def test_direct_flag(self):
        decider = ReplyDecider(make_config(), None, FakeSettings())
        named = asyncio.run(decider.decide(make_message("Rosalie tu es là ?"), []))
        self.assertTrue(named.direct)
        private = asyncio.run(decider.decide(make_message("hey", private=True), []))
        self.assertTrue(private.direct)
        dedicated = ReplyDecider(make_config(channel_ids=frozenset({10})), None, FakeSettings())
        decision = asyncio.run(dedicated.decide(make_message("il fait beau"), []))
        self.assertTrue(decision)
        self.assertFalse(decision.direct)


class LegacyFormatTest(unittest.TestCase):
    """Les fichiers d'avant la restructuration (ids Discord bruts) sont repris."""

    def test_memory_and_settings_and_agenda(self):
        import json
        from libs.conversation.agenda import Agenda
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "memory").mkdir()
            (root / "memory" / "123.json").write_text(json.dumps(
                [{"author_id": ME, "author_name": "Ethann", "content": "vieux", "is_bot": False}]))
            self.assertEqual([e.content for e in ConversationMemory(root / "memory").get("discord:123")],
                             ["vieux"])
            self.assertTrue((root / "memory" / "discord_123.json").exists())

            (root / "settings.json").write_text(json.dumps({"channel_ids": [7]}))
            self.assertEqual(Settings(root / "settings.json").dedicated, {"discord:7"})

            (root / "agenda.json").write_text(json.dumps({"next_id": 2, "home": [10, ME], "followups": [
                {"id": 1, "channel_id": 10, "user_id": ME, "due": 0, "intention": "x", "created": 0}]}))
            agenda = Agenda(root / "agenda.json")
            self.assertEqual(agenda.home, ("discord:10", f"discord:{ME}"))
            self.assertEqual(agenda.pending()[0].conversation, "discord:10")


if __name__ == "__main__":
    unittest.main()
