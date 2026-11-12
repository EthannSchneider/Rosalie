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
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=42, name="Ethann"))
        result = asyncio.run(tools.execute(ctx, "send_message", {"channel": "Le Bunker", "content": "Salut !"}))
        self.assertIn("Message envoyé", result)
        self.assertEqual(bunker.text_channels[1].sent, ["Salut !"])
        self.assertIn("n'existe pas", asyncio.run(tools.execute(ctx, "hack", {})))
        self.assertIn("manquant", asyncio.run(tools.execute(ctx, "send_message", {"channel": "x"})))
        self.assertIn("Aucun salon", asyncio.run(
            tools.execute(ctx, "send_message", {"channel": "inconnu", "content": "x"})))

    def test_dangerous_tool_needs_confirmation(self):
        bot, _, _ = make_bot()
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=42, name="Ethann"))
        with mock.patch.object(tools, "ask_confirmation", mock.AsyncMock(return_value=False)) as ask:
            result = asyncio.run(tools.execute(ctx, "delete_channel", {"channel": "memes"}))
        ask.assert_awaited_once()
        self.assertIn("annulée", result)

    def test_guest_cannot_act(self):
        bot, _, _ = make_bot()
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=7, name="Sachiko"))
        with mock.patch.object(tools, "ask_confirmation", mock.AsyncMock(return_value=True)) as ask:
            for name, args in [("delete_channel", {"channel": "memes"}),
                               ("send_dm", {"user": "x", "content": "y"}),
                               ("recall", {"query": "adresse"})]:
                self.assertIn("seul mon créateur", asyncio.run(tools.execute(ctx, name, args)))
        ask.assert_not_awaited()
        names = {s["function"]["name"] for s in tools.schemas(guest=True)}
        self.assertEqual(names, tools.GUEST_TOOLS)

    def test_schemas_are_valid(self):
        for schema in tools.schemas():
            function = schema["function"]
            for name in function["parameters"]["required"]:
                self.assertIn(name, function["parameters"]["properties"])


class WebTest(unittest.TestCase):
    def test_local_network_is_refused(self):
        from libs import web
        for url in ("http://127.0.0.1:11434/api/tags", "http://localhost/", "http://192.168.1.1/",
                    "http://[::1]/", "file:///etc/passwd", "ftp://example.com"):
            with self.assertRaises(web.WebError, msg=url):
                asyncio.run(web._check_public(url))

    def test_text_extraction(self):
        from libs.web import _TextExtractor
        parser = _TextExtractor()
        parser.feed("<html><head><title>Météo</title><style>p{}</style></head><body>"
                    "<nav>menu</nav><svg><title>icone</title></svg><h1>Lausanne</h1><p>12&deg;C, pluie</p>"
                    "<script>alert(1)</script></body></html>")
        self.assertEqual(parser.title, "Météo")
        self.assertEqual(parser.text(), "Lausanne\n12°C, pluie")

    def test_browser_fallback(self):
        from libs import web

        class FakeBrowser:
            def __init__(self):
                self.calls = 0

            async def render(self, url):
                self.calls += 1
                return "App", "\n".join(f"Jour {i} : 14°C, pluie {i} mm" for i in range(80))

        async def no_dns_check(url):
            return None

        js_app = "<html><title>App</title><body><div id='root'></div><script>app()</script></body></html>"
        static = "<html><title>Doc</title><main>" + "".join(
            f"<p>Paragraphe {i} : texte déjà présent dans le HTML.</p>" for i in range(60)) + "</main></html>"
        with mock.patch.object(web, "_check_public", no_dns_check):
            for body, expected_calls, expected in ((js_app, 1, "14°C"), (static, 0, "déjà présent")):
                browser = FakeBrowser()
                with mock.patch.object(web, "_download", mock.AsyncMock(
                        return_value=("https://x.ch", "text/html", body))):
                    title, text = asyncio.run(web.fetch("https://x.ch", browser=browser))
                self.assertEqual(browser.calls, expected_calls)
                self.assertIn(expected, text)

            # anti-robot (403) : le navigateur prend le relais ; mode never : pas de navigateur
            browser = FakeBrowser()
            with mock.patch.object(web, "_download", mock.AsyncMock(
                    side_effect=web.WebError("HTTP 403", status=403))):
                self.assertIn("14°C", asyncio.run(web.fetch("https://x.ch", browser=browser))[1])
                with self.assertRaises(web.WebError):
                    asyncio.run(web.fetch("https://x.ch", browser=browser, mode="never"))

    def test_web_tools_can_be_disabled(self):
        bot, _, _ = make_bot()
        bot.config.web_access = False
        names = [s["function"]["name"] for s in tools.schemas(False)]
        self.assertNotIn("web_search", names)
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=42, name="Ethann"))
        self.assertIn("désactivé", asyncio.run(tools.execute(ctx, "web_search", {"query": "x"})))


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
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=42, name="Ethann"))
        result = asyncio.run(run_agent(llm, [{"role": "user", "content": "dis bonjour"}], ctx))
        self.assertEqual(result.text, "C'est envoyé !")
        self.assertEqual(len(result.actions), 1)
        self.assertEqual(llm.seen[1][-1]["role"], "tool")
        # La trace (appel + résultat) est renvoyée pour être gardée dans l'historique
        self.assertEqual([m["role"] for m in result.trace], ["assistant", "tool"])
        self.assertEqual(result.trace[0]["tool_calls"][0]["function"]["arguments"]["content"], "Hello")

    def test_sent_message_is_recorded_in_target_channel(self):
        from libs.conversation.memory import ConversationMemory
        bot, bunker, _ = make_bot()
        target = bunker.text_channels[1]
        target.send = lambda content: asyncio.sleep(0, SimpleNamespace(id=777, channel=target))
        with tempfile.TemporaryDirectory() as directory:
            bot.memory = ConversationMemory(Path(directory))
            bot.user = SimpleNamespace(id=1, display_name="Rosalie")
            ctx = tools.ToolContext(bot=bot, channel=SimpleNamespace(id=5),
                                    author=SimpleNamespace(id=42, name="Ethann", display_name="Ethann"))
            asyncio.run(tools.execute(ctx, "send_message", {"channel": "Le Bunker", "content": "Salut !"}))
            entries = bot.memory.get(target.id)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].content, "Salut !")
            self.assertTrue(entries[0].is_bot)
            self.assertEqual(bot.memory.get(5), [])   # rien en double dans le salon d'origine

    def test_announced_action_is_nudged_once(self):
        bot, _, _ = make_bot()
        llm = FakeLLM([{"content": "Je vais vérifier ça."}, {"content": "Il fait 12°C."}])
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=42, name="Ethann"))
        result = asyncio.run(run_agent(llm, [{"role": "user", "content": "météo ?"}], ctx))
        self.assertEqual(result.text, "Il fait 12°C.")
        self.assertIn("Note système", llm.seen[1][-1]["content"])
        llm = FakeLLM([{"content": "Je vais vérifier."}, {"content": "Je vais encore vérifier."}])
        result = asyncio.run(run_agent(llm, [{"role": "user", "content": "météo ?"}], ctx))
        self.assertEqual(result.text, "Je vais encore vérifier.")

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


class ToolErrorsTest(unittest.TestCase):
    def test_errors_are_collected_and_shown(self):
        from cogs.rosalie.chat import _errors_footer

        class LLM:
            def __init__(self):
                self.replies = [
                    {"content": "", "tool_calls": [{"function": {"name": "read_messages",
                                                                 "arguments": {"channel": "inconnu"}}}]},
                    {"content": "Voilà les messages !"}]

            async def chat_message(self, messages, tools=None):
                return self.replies.pop(0)

        bot, _, _ = make_bot()
        bot.config.web_access = True
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=42, name="Ethann"))
        result = asyncio.run(run_agent(LLM(), [{"role": "system", "content": "S"}], ctx))
        self.assertEqual(len(result.errors), 1)
        self.assertTrue(result.errors[0].startswith("read_messages : Aucun salon"))
        footer = _errors_footer(result.errors * 2)
        self.assertTrue(footer.startswith("⚠️ Une action a échoué"))
        self.assertIn("`read_messages`", footer)

    def test_unknown_id_is_fetched_from_discord(self):
        bot, bunker, _ = make_bot()
        thread = FakeChannel(1262590550873264644, "un-fil", bunker)
        bot.fetch_channel = mock.AsyncMock(return_value=thread)
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=42, name="Ethann"))
        asyncio.run(tools.execute(ctx, "send_message", {"channel": "1262590550873264644", "content": "coucou"}))
        self.assertEqual(thread.sent, ["coucou"])

        bot.fetch_channel = mock.AsyncMock(side_effect=discord.NotFound(
            SimpleNamespace(status=404, reason="Not Found"), "Unknown Channel"))
        result = asyncio.run(tools.execute(ctx, "read_messages", {"channel": "1262590550873264644"}))
        self.assertIn("ne correspond à aucun salon que je peux voir", result)


class ContextFitTest(unittest.TestCase):
    def test_big_tool_results_are_shrunk_first(self):
        from libs.assistant.agent import fit_context
        messages = [{"role": "system", "content": "S" * 100},
                    {"role": "user", "content": "lis les salons"},
                    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_messages"}}]},
                    {"role": "tool", "content": "x" * 9000, "tool_name": "read_messages"}]
        self.assertTrue(fit_context(messages, 3000))
        self.assertEqual(len(messages), 4)
        self.assertLess(len(messages[3]["content"]), 3000)
        self.assertIn("coupé", messages[3]["content"])

    def test_old_history_is_dropped_but_never_the_question(self):
        from libs.assistant.agent import fit_context
        messages = [{"role": "system", "content": "S"},
                    {"role": "user", "content": "vieux " * 400},
                    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "x"}}]},
                    {"role": "tool", "content": "r", "tool_name": "x"},
                    {"role": "assistant", "content": "ancienne réponse " * 100},
                    {"role": "user", "content": "la vraie question"}]
        fit_context(messages, 500)
        self.assertEqual(messages[0]["content"], "S")
        self.assertEqual(messages[-1]["content"], "la vraie question")
        self.assertEqual([m["role"] for m in messages], ["system", "user"])

    def test_truncated_reply_is_flagged(self):
        class LLM:
            async def chat_message(self, messages, tools=None):
                return {"content": "Voici ce que", "done_reason": "length"}

        bot, _, _ = make_bot()
        bot.config.web_access = True
        ctx = tools.ToolContext(bot=bot, channel=None, author=SimpleNamespace(id=42, name="Ethann"))
        result = asyncio.run(run_agent(LLM(), [{"role": "system", "content": "S"},
                                               {"role": "user", "content": "q"}], ctx))
        self.assertIn("coupée", result.text)


class ListMembersTest(unittest.TestCase):
    def test_list_members(self):
        bot, bunker, _ = make_bot()
        everyone = SimpleNamespace(name="@everyone", is_default=lambda: True)
        admin = SimpleNamespace(name="Admin", is_default=lambda: False)
        member = lambda name, display, is_bot=False, roles=(): SimpleNamespace(
            name=name, display_name=display, bot=is_bot, roles=[everyone, *roles])
        bunker.members = [member("ethann69", "Senior Ethann", roles=[admin]), member("diogo", "diogo"),
                          member("rosalie", "Rosalie", is_bot=True)]
        bunker.member_count = 3
        ctx = tools.ToolContext(bot=bot, channel=bunker.text_channels[0], author=SimpleNamespace(id=42, name="E"))
        result = asyncio.run(tools.execute(ctx, "list_members", {}))
        self.assertIn("2 personne(s), 1 bot(s)", result)
        self.assertIn("- Senior Ethann (@ethann69) — Admin", result)
        self.assertIn("Bots : Rosalie", result)
