import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from libs.config import ROOT_DIR
from finetune.dataset.converter import (clean, convert, load_discord, load_whatsapp, to_samples,
                                       to_turns, whatsapp_authors, write_samples)

ME, THEM = "1", "2"
AUTHORS = {ME: {"id": ME, "username": "ethann", "global_name": "Ethann"},
           THEM: {"id": THEM, "username": "alex", "global_name": "Alex"}}


def message(id, author, content, minute, type=0):
    return {"id": str(id), "type": type, "author": AUTHORS[author], "content": content,
            "timestamp": f"2026-11-01T10:{minute:02d}:00+00:00"}


CHAT = [
    message(100, ME, "salut", 0),
    message(101, ME, "t'es là ?", 1),
    message(102, THEM, "oui ! ça va et toi", 2),
    message(103, ME, "bien, regarde https://exemple.ch", 3),
    message(104, THEM, "trop cool", 4),
    message(105, THEM, "écris-moi à alex@mail.ch ou au +41 79 123 45 67", 5),
    message(106, ME, "", 6),                       # pièce jointe seule
    message(107, ME, "a rejoint l'appel", 7, type=3),
]


def discord(messages):
    """Écrit les messages comme messages.txt puis les relit avec load_discord."""
    directory = tempfile.mkdtemp()
    path = Path(directory) / "messages.txt"
    path.write_text("\n".join(json.dumps(m) for m in messages), encoding="utf-8")
    return load_discord(path)


class ConverterTest(unittest.TestCase):
    def test_turns_are_merged_and_cleaned(self):
        sessions = to_turns(discord(CHAT))
        self.assertEqual(len(sessions), 1)
        texts = [turn.text for turn in sessions[0]]
        self.assertEqual(texts[0], "salut\nt'es là ?")
        self.assertEqual(texts[2], "bien, regarde [lien]")
        self.assertEqual(texts[3], "trop cool\nécris-moi à [email] ou au [téléphone]")

    def test_mentions(self):
        self.assertEqual(clean("coucou <@2> <:pepe:123>", {"2": "Alex"}), "coucou @Alex :pepe:")

    def test_samples_for_them(self):
        samples = to_samples(to_turns(discord(CHAT)), THEM)
        self.assertEqual(len(samples), 2)
        last = samples[-1]["messages"]
        self.assertEqual([m["role"] for m in last], ["user", "assistant", "user", "assistant"])
        self.assertTrue(last[-1]["content"].startswith("trop cool"))

    def test_samples_for_me_start_with_user(self):
        samples = to_samples(to_turns(discord(CHAT)), ME)
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["messages"][0]["role"], "user")

    def test_long_pause_splits_conversations(self):
        late = dict(message(200, THEM, "re", 0), timestamp="2026-11-02T10:00:00+00:00")
        later = dict(message(201, ME, "re !", 0), timestamp="2026-11-02T10:01:00+00:00")
        self.assertEqual(len(to_turns(discord(CHAT + [late, later]))), 2)

    def test_convert_dedupes_and_sorts(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "messages.txt"
            lines = [json.dumps(m) for m in reversed(CHAT)] + [json.dumps(CHAT[2])]
            source.write_text("\n".join(lines), encoding="utf-8")
            sessions, samples = convert(source, Path(directory) / "out.jsonl", [THEM])
            self.assertEqual((sessions, samples), (1, 2))
            # les deux points de vue : 2 exemples côté Alex + 1 côté Ethann
            self.assertEqual(convert(source, Path(directory) / "out.jsonl", [ME, THEM]), (1, 3))


WHATSAPP_IOS = """\u200e[26.05.2021, 07:33:12] Alex: \u200eMessages and calls are end-to-end encrypted. Only people in this chat can read them.
[26.05.2021, 07:34:00] Ethann Schneider: salut
[26.05.2021, 07:34:10] Ethann Schneider: tu viens ce soir ?
[26.05.2021, 07:35:00] Alex: ouiii
trop hâte
\u200e[26.05.2021, 07:35:05] Alex: \u200eimage omitted
[26.05.2021, 07:35:30] Alex: regarde \u200eimage omitted
[26.05.2021, 07:36:00] Ethann Schneider: \u200eThis message was deleted.
[26.05.2021, 07:36:10] Ethann Schneider: appelle moi au +41 79 123 45 67
\u200e[26.05.2021, 07:40:00] Alex: \u200eMissed voice call' \u200eTap to call back
[26.05.2021, 07:41:00] Alex: ok ça marche<This message was edited>
"""

WHATSAPP_ANDROID = """26.05.21, 07:34 - Ethann Schneider: salut
26.05.21, 07:35 - Alex: coucou
26.05.21, 07:36 - Ethann Schneider: <Media omitted>
26.05.21, 07:37 - Ethann Schneider: ça va ?
"""


class WhatsAppTest(unittest.TestCase):
    def write(self, content, name="_chat.txt"):
        path = Path(tempfile.mkdtemp()) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_ios_export(self):
        path = self.write(WHATSAPP_IOS)
        self.assertEqual(whatsapp_authors(path), {"Alex", "Ethann Schneider"})
        texts = [(m.author, m.text) for m in load_whatsapp(path)]
        self.assertEqual(texts, [
            ("Ethann Schneider", "salut"),
            ("Ethann Schneider", "tu viens ce soir ?"),
            ("Alex", "ouiii\ntrop hâte"),
            ("Alex", "regarde"),
            ("Ethann Schneider", "appelle moi au [téléphone]"),
            ("Alex", "ok ça marche"),
        ])
        sessions = to_turns(load_whatsapp(path))
        self.assertEqual([t.author for t in sessions[0]], ["Ethann Schneider", "Alex", "Ethann Schneider", "Alex"])
        with tempfile.TemporaryDirectory() as directory:
            result = write_samples(load_whatsapp(path), Path(directory) / "o.jsonl", ["Alex", "Ethann Schneider"])
            self.assertEqual(result, (1, 3))

    def test_android_export_and_zip(self):
        import zipfile
        source = self.write(WHATSAPP_ANDROID)
        archive = source.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.write(source, "_chat.txt")
        texts = [(m.author, m.text) for m in load_whatsapp(archive)]
        self.assertEqual(texts, [("Ethann Schneider", "salut"), ("Alex", "coucou"),
                                 ("Ethann Schneider", "ça va ?")])


class ExportLoopTest(unittest.TestCase):
    def load_script(self):
        spec = importlib.util.spec_from_file_location("export_discord", ROOT_DIR / "finetune" / "collect" / "export_discord.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_network_errors_wait_and_retry(self):
        import io
        import urllib.error
        script = self.load_script()

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        outcomes = [urllib.error.URLError(ConnectionResetError(54, "Connection reset by peer")),
                    TimeoutError("timed out"),
                    urllib.error.HTTPError("u", 502, "Bad Gateway", {}, io.BytesIO(b"")),
                    Response(b'[{"id": "1"}]')]

        def fake_urlopen(req, timeout):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(script.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(script.time, "sleep") as sleep:
            self.assertEqual(script.request("/x", "token"), [{"id": "1"}])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [30, 60, 120])

    def test_pages_with_before_and_pauses(self):
        script = self.load_script()
        history = [message(1000 - i, THEM if i % 2 else ME, f"m{i}", 0) for i in range(120)]  # récent -> ancien
        queries = []

        def fake_request(path, token):
            queries.append(path)
            before = int(path.split("before=")[1]) if "before=" in path else None
            older = [m for m in history if before is None or int(m["id"]) < before]
            return older[:script.BATCH]

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(script, "request", fake_request), \
                mock.patch.object(script.time, "sleep") as sleep:
            path = Path(directory) / "messages.txt"
            script.export("42", "token", path)
            saved = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(saved), 120)
            self.assertEqual(queries, ["/channels/42/messages?limit=50",
                                       "/channels/42/messages?limit=50&before=951",
                                       "/channels/42/messages?limit=50&before=901"])
            self.assertEqual(sleep.call_count, 2)
            self.assertTrue(all(1 <= call.args[0] <= 20 for call in sleep.call_args_list))

            # relance : reprend depuis le plus ancien message déjà sauvegardé
            queries.clear()
            script.export("42", "token", path)
            self.assertEqual(queries, ["/channels/42/messages?limit=50&before=881"])


if __name__ == "__main__":
    unittest.main()
