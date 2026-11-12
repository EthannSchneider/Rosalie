import asyncio
import datetime
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from libs.assistant.tools import execute, schemas
from libs.conversation.agenda import Agenda
from libs.conversation.initiative import (in_quiet_hours, is_silence, parse_hours,
                                          reflection_skip_reason, with_note)
from libs.conversation.prompt import build_system_prompt

ME = 42
NOW = datetime.datetime(2026, 11, 12, 15, 0).timestamp()


def skip(**overrides):
    values = dict(enabled=True, quiet=(23, 8), last_activity=NOW - 3 * 3600,
                  last_reflection=NOW - 3600, last_was_spontaneous=False, initiatives_today=0,
                  every_minutes=45, min_silence_minutes=60, max_per_day=3)
    values.update(overrides)
    return reflection_skip_reason(NOW, **values)


class SilenceTest(unittest.TestCase):
    def test_silence_markers(self):
        for text in ("[SILENCE]", " [silence] ", "SILENCE", "", "…", "[SILENCE] rien à dire"):
            self.assertTrue(is_silence(text), text)

    def test_normal_reply_is_not_silence(self):
        self.assertFalse(is_silence("Le silence est d'or, tu sais."))
        self.assertFalse(is_silence("ok"))


class QuietHoursTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_hours("23-8"), (23, 8))
        self.assertIsNone(parse_hours(""))
        self.assertIsNone(parse_hours("n'importe quoi"))

    def test_wraps_midnight(self):
        quiet = (23, 8)
        at = lambda hour: datetime.datetime(2026, 1, 1, hour)
        self.assertTrue(in_quiet_hours(at(23), quiet))
        self.assertTrue(in_quiet_hours(at(3), quiet))
        self.assertFalse(in_quiet_hours(at(8), quiet))
        self.assertFalse(in_quiet_hours(at(15), quiet))
        self.assertTrue(in_quiet_hours(at(14), (13, 15)))


class ReflectionPolicyTest(unittest.TestCase):
    def test_can_reflect(self):
        self.assertIsNone(skip())

    def test_reasons_to_stay_quiet(self):
        self.assertIsNotNone(skip(enabled=False))
        self.assertIsNotNone(skip(last_reflection=NOW - 60))
        self.assertIsNotNone(skip(last_activity=NOW - 600))
        self.assertIsNotNone(skip(last_was_spontaneous=True))
        self.assertIsNotNone(skip(initiatives_today=3))
        self.assertIsNotNone(skip(quiet=(14, 16)))


class AgendaTest(unittest.TestCase):
    def test_add_pop_cancel_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agenda.json"
            agenda = Agenda(path)
            first = agenda.add(10, ME, 60, "lui rappeler sa lessive", now=NOW)
            second = agenda.add(10, ME, 3600, "prendre des nouvelles", now=NOW)
            agenda.set_home(10, ME)

            reloaded = Agenda(path)
            self.assertEqual([f.id for f in reloaded.pending(10)], [first.id, second.id])
            self.assertEqual(reloaded.home, (10, ME))
            self.assertEqual(reloaded.pop_due(NOW + 30), [])
            self.assertEqual([f.id for f in reloaded.pop_due(NOW + 120)], [first.id])
            self.assertEqual(reloaded.pop_due(NOW + 120), [])   # une seule fois
            self.assertTrue(reloaded.cancel(second.id))
            self.assertFalse(reloaded.cancel(second.id))
            self.assertEqual(Agenda(path).pending(), [])

    def test_initiative_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            agenda = Agenda(Path(tmp) / "agenda.json")
            agenda.mark_initiative(NOW - 90000)
            agenda.mark_initiative(NOW)
            self.assertEqual(agenda.initiatives_since(NOW - 86400), 1)


class InitiativeToolsTest(unittest.TestCase):
    def make_ctx(self, tmp, author_id=ME):
        sent = []

        async def send(content):
            sent.append(content)
            return SimpleNamespace(id=1, channel=None)

        bot = SimpleNamespace(config=SimpleNamespace(owner_ids={ME}, web_access=True),
                              agenda=Agenda(Path(tmp) / "agenda.json"))
        ctx = SimpleNamespace(bot=bot, channel=SimpleNamespace(id=10, send=send),
                              author=SimpleNamespace(id=author_id), is_owner=author_id == ME)
        return ctx, sent

    def test_plan_and_cancel_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _ = self.make_ctx(tmp)
            result = asyncio.run(execute(ctx, "plan_followup",
                                         {"minutes": 10, "intention": "rappel lessive"}))
            self.assertIn("Relance programmée", result)
            [followup] = ctx.bot.agenda.pending(10)
            self.assertEqual(followup.user_id, ME)
            result = asyncio.run(execute(ctx, "cancel_followup", {"followup_id": followup.id}))
            self.assertEqual(result, "Relance annulée.")

    def test_say_sends_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, sent = self.make_ctx(tmp)
            asyncio.run(execute(ctx, "say", {"content": "Je regarde ça !"}))
            self.assertEqual(sent, ["Je regarde ça !"])

    def test_guests_cannot_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, _ = self.make_ctx(tmp, author_id=99)
            asyncio.run(execute(ctx, "plan_followup", {"minutes": 1, "intention": "spam"}))
            self.assertEqual(ctx.bot.agenda.pending(), [])
            names = {s["function"]["name"] for s in schemas(guest=True)}
            self.assertNotIn("plan_followup", names)
            self.assertNotIn("say", names)


class PromptTest(unittest.TestCase):
    def test_note_is_merged_or_appended(self):
        messages = with_note([{"role": "system", "content": "S"}, {"role": "user", "content": "hey"}],
                             "NOTE")
        self.assertEqual(messages[-1]["content"], "hey\n\nNOTE")
        messages = with_note([{"role": "system", "content": "S"},
                              {"role": "assistant", "content": "yo"}], "NOTE")
        self.assertEqual(messages[-1], {"role": "user", "content": "NOTE"})

    def test_prompt_mentions_silence_and_followups(self):
        prompt = build_system_prompt("PERSONA", "Rosalie", "DM", speaker="Ethann",
                                     followups=["#3 à 12.11 18:00 (dans 60 min) : rappel"])
        self.assertIn("[SILENCE]", prompt)
        self.assertIn("plan_followup", prompt)
        self.assertIn("#3 à 12.11 18:00", prompt)
        guest = build_system_prompt("PERSONA", "Rosalie", "DM", speaker="X", guest=True)
        self.assertNotIn("plan_followup", guest)


if __name__ == "__main__":
    unittest.main()
