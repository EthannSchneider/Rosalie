import asyncio
import datetime
import unittest
from types import SimpleNamespace
from unittest import mock

import discord

from libs.assistant import tools
from libs.assistant.tools.utilities import format_weather

OWNER, OTHER, BOT = 42, 7, 1


class FakeMessage:
    def __init__(self, id, author_id, content="", channel=None):
        self.id, self.channel = id, channel
        self.author = SimpleNamespace(id=author_id, name=f"u{author_id}", display_name=f"User{author_id}")
        self.clean_content = content
        self.created_at = datetime.datetime(2026, 11, 12, 15, 0)
        self.reactions, self.pinned, self.deleted, self.edited = [], False, False, None

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

    async def pin(self):
        self.pinned = True

    async def delete(self):
        self.deleted = True

    async def edit(self, content):
        self.edited = content


class FakeChannel:
    def __init__(self, id=1262590550873264644):
        self.id, self.name, self.guild = id, "général", None
        self.messages = []   # du plus ancien au plus récent
        self.sent = []

    async def history(self, limit=100):
        for message in reversed(self.messages[-limit:]):
            yield message

    async def fetch_message(self, message_id):
        for message in self.messages:
            if message.id == message_id:
                return message
        raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))
        return SimpleNamespace(id=5, channel=self)


def make_ctx(channel, disabled=()):
    config = SimpleNamespace(owner_ids={OWNER}, web_access=True, disabled_tools=disabled)
    bot = SimpleNamespace(config=config, user=SimpleNamespace(id=BOT), memory=None, guilds=[],
                          get_channel=lambda i: channel if i == channel.id else None)
    return tools.ToolContext(bot=bot, channel=channel, author=SimpleNamespace(id=OWNER))


def run(ctx, name, args):
    return asyncio.run(tools.execute(ctx, name, args))


class MessageToolsTest(unittest.TestCase):
    def setUp(self):
        self.channel = FakeChannel()
        self.mine = FakeMessage(100000000000000001, OWNER, "on mange quoi ce soir ?", self.channel)
        self.other = FakeMessage(100000000000000002, OTHER, "pizza !", self.channel)
        self.rosalie = FakeMessage(100000000000000003, BOT, "Bonne idée", self.channel)
        self.channel.messages = [self.mine, self.other, self.rosalie]
        self.ctx = make_ctx(self.channel)

    def test_react_to_my_last_message_by_default(self):
        self.assertIn("Réaction", run(self.ctx, "react", {"emoji": "👍"}))
        self.assertEqual(self.mine.reactions, ["👍"])

    def test_last_skips_rosalie_and_link_works(self):
        run(self.ctx, "react", {"emoji": "😂", "message": "dernier"})
        self.assertEqual(self.other.reactions, ["😂"])
        link = f"https://discord.com/channels/9/{self.channel.id}/{self.mine.id}"
        run(self.ctx, "pin_message", {"message": link})
        self.assertTrue(self.mine.pinned)

    def test_edit_only_own_messages(self):
        self.assertIn("modifié", run(self.ctx, "edit_message",
                                      {"message": str(self.rosalie.id), "content": "Super idée"}))
        self.assertEqual(self.rosalie.edited, "Super idée")
        self.assertIn("Erreur", run(self.ctx, "edit_message",
                                     {"message": str(self.other.id), "content": "x"}))

    def test_delete_needs_confirmation(self):
        with mock.patch.object(tools.base, "ask_confirmation", mock.AsyncMock(return_value=False)):
            run(self.ctx, "delete_message", {"message": str(self.other.id)})
        self.assertFalse(self.other.deleted)
        with mock.patch.object(tools.base, "ask_confirmation", mock.AsyncMock(return_value=True)):
            run(self.ctx, "delete_message", {"message": str(self.other.id)})
        self.assertTrue(self.other.deleted)

    def test_search_and_unknown_message(self):
        result = run(self.ctx, "search_messages", {"query": "PIZZA"})
        self.assertIn("pizza !", result)
        self.assertIn(str(self.other.id), result)
        self.assertIn("introuvable", run(self.ctx, "react", {"emoji": "👍", "message": "123456789012345678"}))

    def test_poll(self):
        self.assertIn("Sondage créé (3 réponses",
                      run(self.ctx, "create_poll", {"question": "Ce soir ?", "answers": "Pizza | Sushi | Raclette"}))
        poll = self.channel.sent[-1][1]["poll"]
        self.assertEqual([a.text for a in poll.answers], ["Pizza", "Sushi", "Raclette"])
        self.assertIn("Erreur", run(self.ctx, "create_poll", {"question": "?", "answers": "Seule"}))

    def test_disabled_tools(self):
        ctx = make_ctx(self.channel, disabled=("react",))
        self.assertIn("désactivé", run(ctx, "react", {"emoji": "👍"}))
        names = {s["function"]["name"] for s in tools.schemas(disabled=("react",))}
        self.assertNotIn("react", names)
        self.assertIn("pin_message", names)


class WeatherTest(unittest.TestCase):
    def test_format(self):
        text = format_weather(
            {"name": "Lausanne", "admin1": "Vaud", "country": "Suisse"},
            {"current": {"temperature_2m": 12.4, "apparent_temperature": 11, "weather_code": 61,
                         "wind_speed_10m": 5},
             "daily": {"time": ["2026-11-12"], "temperature_2m_min": [8], "temperature_2m_max": [13],
                       "weather_code": [3], "precipitation_probability_max": [40]}})
        self.assertIn("Lausanne, Vaud, Suisse", text)
        self.assertIn("12.4°C", text)
        self.assertIn("pluie faible", text)
        self.assertIn("jeudi 12.11 : 8° / 13°C, couvert, pluie 40 %", text)

    def test_guests_get_weather_only(self):
        names = {s["function"]["name"] for s in tools.schemas(guest=True)}
        self.assertEqual(names, {"web_search", "fetch_url", "weather"})


if __name__ == "__main__":
    unittest.main()
