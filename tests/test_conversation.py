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
from libs.utils.discord_utils import split_message

BOT_ID = 1
ME = 42
OTHER = 99


def make_config(**overrides) -> Config:
    with mock.patch.dict("os.environ", {}, clear=True):
        config = Config.from_env()
    values = {**config.__dict__, "owner_ids": frozenset({ME}), "use_llm_decider": False, **overrides}
    return Config(**values)


def make_message(content, author_id=ME, mentions=(), channel=None, reference=None):
    return SimpleNamespace(
        content=content,
        author=SimpleNamespace(id=author_id, bot=False, display_name="Ethann"),
        mentions=list(mentions),
        attachments=[],
        channel=channel or SimpleNamespace(id=10),
        reference=reference,
    )


class FakeSettings:
    channel_ids: set = set()


class DeciderTest(unittest.TestCase):
    def setUp(self):
        self.bot_user = SimpleNamespace(id=BOT_ID, display_name="Rosalie")

    def decide(self, message, config=None, decider=None):
        decider = decider or ReplyDecider(config or make_config(), None, FakeSettings())
        return asyncio.run(decider.decide(message, self.bot_user, []))

    def test_name_triggers_reply(self):
        self.assertTrue(self.decide(make_message("hey Rosalie tu fais quoi")))

    def test_name_inside_word_does_not_trigger(self):
        self.assertFalse(self.decide(make_message("rosaliesoft est cool")))

    def test_mention_triggers_reply(self):
        self.assertTrue(self.decide(make_message("salut", mentions=[self.bot_user])))

    def test_random_message_ignored(self):
        self.assertFalse(self.decide(make_message("quelqu'un joue ce soir ?")))

    def test_ignore_prefix(self):
        self.assertFalse(self.decide(make_message("// rosalie chut")))

    def test_only_owner_when_public_replies_off(self):
        config = make_config(public_replies=False)
        self.assertFalse(self.decide(make_message("rosalie ?", author_id=OTHER), config))
        self.assertTrue(self.decide(make_message("rosalie ?", author_id=ME), config))
        self.assertFalse(self.decide(make_message("rosalie ?"), make_config(
            owner_ids=frozenset(), public_replies=False)))

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
        other = SimpleNamespace(id=OTHER)
        self.assertFalse(self.decide(make_message("tu viens ?", mentions=[other]), config))

    def test_active_conversation(self):
        decider = ReplyDecider(make_config(), None, FakeSettings())
        self.assertFalse(self.decide(make_message("et ensuite ?"), decider=decider))
        decider.mark_active(10, ME)
        self.assertTrue(self.decide(make_message("et ensuite ?"), decider=decider))
        decider.stop(10)
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

    def test_system_prompt_contains_memories(self):
        prompt = build_system_prompt("PERSONA", "Rosalie", "DM", servers=["Le Bunker"],
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
                memory.add(5, Entry(ME, "Ethann", f"m{index}", False, message_id=index))
            reloaded = ConversationMemory(Path(directory), max_size=2)
            self.assertEqual([e.content for e in reloaded.get(5)], ["m1", "m2"])
            context, entry = reloaded.before(5, 2)
            self.assertEqual(entry.content, "m2")
            self.assertEqual(len(context), 1)


class SplitTest(unittest.TestCase):
    def test_split(self):
        text = ("a" * 1500 + "\n") * 3
        chunks = split_message(text)
        self.assertTrue(all(len(chunk) <= 2000 for chunk in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), "a" * 4500)


if __name__ == "__main__":
    unittest.main()
