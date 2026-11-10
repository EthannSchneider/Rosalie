import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import discord

from libs.assistant import tools
from libs.assistant.agent import _inline_tool_calls, run_agent
from libs.assistant.resolver import ResolveError, normalize, resolve_channel, resolve_guild
from libs.llm.ollama import OllamaError
from libs.memory.long_term import LongTermMemory


class FakeChannel:
    def __init__(self, id, name, guild):
        self.id, self.name, self.guild = id, name, guild
        self.sent = []

    async def send(self, content):
        self.sent.append(content)
        return SimpleNamespace(id=999)

    def permissions_for(self, member):
        return SimpleNamespace(send_messages=True)


class FakeGuild:
    def __init__(self, id, name, channel_names):
        self.id, self.name = id, name
        self.me = object()
        self.text_channels = [FakeChannel(id * 100 + i, n, self) for i, n in enumerate(channel_names)]
        self.channels = list(self.text_channels)
        self.system_channel = None


def make_bot():
    bunker = FakeGuild(1, "Le Bunker", ["règles", "général", "memes"])
    hydromel = FakeGuild(2, "Compagnie Hydromel", ["général", "bar-du-bunker"])
    guilds = [bunker, hydromel]
    channels = {c.id: c for g in guilds for c in g.channels}
    bot = SimpleNamespace(
        guilds=guilds,
        get_guild=lambda i: next((g for g in guilds if g.id == i), None),
        get_channel=channels.get,
        config=SimpleNamespace(owner_ids=frozenset({42})),
    )
    return bot, bunker, hydromel


class ResolverTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("Le Bunker"), normalize("le-bunker"))
        self.assertEqual(normalize("Général"), "general")

    def test_server_name_goes_to_default_channel(self):
        bot, bunker, _ = make_bot()
        channel = resolve_channel(bot, "Le bunker", None)
        self.assertEqual(channel.guild, bunker)
        self.assertEqual(channel.name, "général")

    def test_exact_channel(self):
        bot, bunker, _ = make_bot()
        self.assertEqual(resolve_channel(bot, "#memes", None).guild, bunker)

    def test_ambiguous_channel_raises(self):
        bot, _, _ = make_bot()
        with self.assertRaises(ResolveError) as error:
            resolve_channel(bot, "général", None)
        self.assertIn("Plusieurs", str(error.exception))

    def test_server_slash_channel(self):
        bot, _, hydromel = make_bot()
        self.assertEqual(resolve_channel(bot, "Compagnie Hydromel/général", None).guild, hydromel)

    def test_here(self):
        bot, _, _ = make_bot()
        current = object()
        self.assertIs(resolve_channel(bot, "ici", current), current)

    def test_guild_needs_precision_in_dm(self):
        bot, _, _ = make_bot()
        with self.assertRaises(ResolveError):
            resolve_guild(bot, None, None)


class ExecuteTest(unittest.TestCase):
    def test_send_message_and_errors(self):
        bot, bunker, _ = make_bot()
        ctx = tools.ToolContext(bot=bot, channel=None, author="Ethann")
        result = asyncio.run(tools.execute(ctx, "send_message", {"channel": "Le Bunker", "content": "Salut !"}))
        self.assertIn("Message envoyé", result)
        self.assertEqual(bunker.text_channels[1].sent, ["Salut !"])
        self.assertIn("n'existe pas", asyncio.run(tools.execute(ctx, "hack", {})))
        self.assertIn("manquant", asyncio.run(tools.execute(ctx, "send_message", {"channel": "x"})))
        self.assertIn("Aucun salon", asyncio.run(
            tools.execute(ctx, "send_message", {"channel": "inconnu", "content": "x"})))

    def test_dangerous_tool_needs_confirmation(self):
        bot, _, _ = make_bot()
        ctx = tools.ToolContext(bot=bot, channel=None, author="Ethann")
        with mock.patch.object(tools, "ask_confirmation", mock.AsyncMock(return_value=False)) as ask:
            result = asyncio.run(tools.execute(ctx, "delete_channel", {"channel": "memes"}))
        ask.assert_awaited_once()
        self.assertIn("annulée", result)

    def test_schemas_are_valid(self):
        for schema in tools.schemas():
            function = schema["function"]
            for name in function["parameters"]["required"]:
                self.assertIn(name, function["parameters"]["properties"])


class FakeLLM:
    """Renvoie une suite de réponses prédéfinies ; embeddings = sac de mots."""

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.seen = []

    async def chat_message(self, messages, tools=None, **_):
        self.seen.append([dict(m) for m in messages])
        return self.replies.pop(0)

    async def embed(self, texts, model):
        vocab = ["anniversaire", "mars", "pizza", "fromages", "chat", "minou"]
        return [[float(word in text.lower()) for word in vocab] + [0.01] for text in texts]


class AgentTest(unittest.TestCase):
    def test_tool_loop(self):
        bot, bunker, _ = make_bot()
        llm = FakeLLM([
            {"content": "", "tool_calls": [{"function": {"name": "send_message",
                                                         "arguments": {"channel": "Le Bunker", "content": "Hello"}}}]},
            {"content": "C'est envoyé !"},
        ])
        ctx = tools.ToolContext(bot=bot, channel=None, author="Ethann")
        result = asyncio.run(run_agent(llm, [{"role": "user", "content": "dis bonjour"}], ctx))
        self.assertEqual(result.text, "C'est envoyé !")
        self.assertEqual(len(result.actions), 1)
        self.assertEqual(llm.seen[1][-1]["role"], "tool")

    def test_inline_json_tool_call(self):
        calls = _inline_tool_calls('{"name": "recall", "parameters": {"query": "pizza"}}')
        self.assertEqual(calls[0]["function"]["name"], "recall")
        self.assertEqual(_inline_tool_calls("Salut !"), [])


class LongTermMemoryTest(unittest.TestCase):
    def test_add_search_dedupe_forget(self):
        async def scenario(path):
            memory = LongTermMemory(path, FakeLLM(), "fake")
            first, _ = await memory.add("Anniversaire d'Ethann : 14 mars", "événement", 5)
            await memory.add("Ethann aime les pizzas 4 fromages", "préférence", 3)
            same, updated = await memory.add("anniversaire le 14 mars", "événement", 5)
            self.assertEqual((same, updated), (first, True))
            found = await memory.search("c'est quand son anniversaire en mars ?")
            self.assertEqual(found[0].id, first)
            self.assertEqual([m.id for m in memory.core()], [first])
            self.assertTrue(memory.forget(first))
            self.assertEqual(memory.count(), 1)
            memory.close()

        with tempfile.TemporaryDirectory() as directory:
            asyncio.run(scenario(Path(directory) / "m.sqlite3"))

    def test_keyword_fallback_when_embeddings_fail(self):
        class Broken(FakeLLM):
            async def embed(self, texts, model):
                raise OllamaError("down")

        async def scenario(path):
            memory = LongTermMemory(path, Broken(), "fake")
            await memory.add("Ethann aime les pizzas 4 fromages")
            self.assertEqual(len(await memory.search("pizzas préférées")), 1)
            memory.close()

        with tempfile.TemporaryDirectory() as directory:
            asyncio.run(scenario(Path(directory) / "m.sqlite3"))


if __name__ == "__main__":
    unittest.main()
