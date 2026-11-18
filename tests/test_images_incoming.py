"""Lecture des images de Discord : l'interface les détecte, le cœur les montre au modèle."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import discord

from libs.assistant.agent import _size, fit_context
from libs.conversation.memory import Entry
from libs.conversation.prompt import build_messages
from libs.core.types import Conversation, Person, to_data_uri
from libs.core.rosalie import Rosalie
from libs.llm.remote import _openai_message
from tests.helpers import FakeDiscord, FakeRosalie

PNG = b"\x89PNG\r\n" + b"x" * 100
JPEG = b"\xff\xd8\xff" + b"y" * 100
PNG_URI = to_data_uri(PNG, "image/png")
JPEG_URI = to_data_uri(JPEG, "image/jpeg")


def make_attachment(filename, content_type, data, spoiler=False):
    return SimpleNamespace(
        filename=filename, content_type=content_type, is_spoiler=spoiler,
        size=len(data),
        read=lambda **_: asyncio.sleep(0, data),
    )


def make_message(attachments=(), content="", message_id=123):
    return SimpleNamespace(
        attachments=list(attachments), clean_content=content, mentions=[],
        reference=None, id=message_id,
    )


class DiscordInterfaceExtractionTest(unittest.TestCase):
    """DiscordInterface.__images_from : détecte, lit et base64 les images (le reste reste texte)."""

    def extract(self, message):
        from interfaces.discord import DiscordInterface
        # name mangling privé de la classe — le helper n'est pas sur InstanceInterface(Interface)
        return list(asyncio.run(DiscordInterface._DiscordInterface__images_from(None, message)))

    def test_images_are_extracted_in_order(self):
        message = make_message(attachments=[
            make_attachment("a.png", "image/png; charset=binary", PNG),
            make_attachment("b.jpg", "image/jpeg", JPEG),
        ])
        self.assertEqual(self.extract(message), [PNG_URI, JPEG_URI])

    def test_non_image_files_are_left_to_the_text(self):
        message = make_message(attachments=[
            make_attachment("cahier.pdf", "application/pdf", b"%PDF"),
            make_attachment("b.jpg", "image/jpeg", JPEG),
        ])
        self.assertEqual(self.extract(message), [JPEG_URI])

    def test_spoilers_are_not_shown(self):
        message = make_message(attachments=[
            make_attachment("s.png", "image/png", PNG, spoiler=True),
            make_attachment("b.jpg", "image/jpeg", JPEG),
        ])
        self.assertEqual(self.extract(message), [JPEG_URI])

    def test_unknown_content_type_is_skipped(self):
        # Sans type image, on n'est pas sûr que ce soit une image : on la laisse au texte
        self.assertEqual(self.extract(make_message(
            attachments=[make_attachment("a", "", PNG)])), [])
        self.assertEqual(self.extract(make_message(
            attachments=[make_attachment("a", "application/octet-stream", PNG)])), [])

    def test_download_errors_are_skipped(self):
        async def broken_read(**_):
            raise discord.HTTPException(SimpleNamespace(status=404, reason="gone"), "404")
        broken = SimpleNamespace(filename="b.png", content_type="image/png", is_spoiler=False,
                                 size=0, read=broken_read)
        message = make_message(attachments=[broken, make_attachment("c.jpg", "image/jpeg", JPEG)])
        self.assertEqual(self.extract(message), [JPEG_URI])

    def test_images_that_are_too_big_are_skipped(self):
        from interfaces.discord import MAX_INCOMING_IMAGE_BYTES
        huge = make_attachment("g.jpg", "image/jpeg", b"\xff\xd8\xff" + b"z" * (MAX_INCOMING_IMAGE_BYTES + 1))
        message = make_message(attachments=[huge, make_attachment("b.jpg", "image/jpeg", JPEG)])
        self.assertEqual(self.extract(message), [JPEG_URI])

    def test_more_than_four_images_are_capped(self):
        from interfaces.discord import MAX_INCOMING_IMAGES
        message = make_message(attachments=[make_attachment(f"n{i}.png", "image/png", PNG)
                                            for i in range(MAX_INCOMING_IMAGES + 2)])
        self.assertEqual(len(self.extract(message)), MAX_INCOMING_IMAGES)

    def test_incoming_from_passes_the_images(self):
        from interfaces.discord import DiscordInterface
        rosalie = FakeRosalie()
        rosalie.discord_permissions = lambda _id: frozenset({"chat"})
        interface = FakeDiscord(rosalie)
        interface.client = SimpleNamespace(user=SimpleNamespace(id=9, name="Rosalie",
                                                                display_name="Rosalie"))
        message = make_message(
            attachments=[make_attachment("a.png", "image/png", PNG)],
            content="regarde !")
        message.channel = SimpleNamespace(id=10, name="general", guild=None,
                                          recipient=SimpleNamespace(name="ethann"))
        message.author = SimpleNamespace(id=42, name="ethann", display_name="Ethann", bot=False)
        message.mentions = []
        incoming = asyncio.run(DiscordInterface.incoming_from(interface, message))
        self.assertEqual(incoming.images, (PNG_URI,))
        self.assertTrue(incoming.has_attachments)
        self.assertIn("a.png", incoming.text)


class BuildMessagesImagesTest(unittest.TestCase):
    """build_messages : les images sont attachées au dernier message de la personne."""

    def test_no_entries_no_image_attached(self):
        # Sans message utilisateur dans l'historique, on ne peut rien rattacher
        self.assertEqual(build_messages("SYS", [], images=(PNG_URI,)),
                         [{"role": "system", "content": "SYS"}])

    def test_images_attached_to_latest_user(self):
        entries = [
            Entry(1, "Ethann", "salut", False),
            Entry(2, "Rosalie", "coucou", True),
            Entry(1, "Ethann", "regarde", False),
        ]
        messages = build_messages("SYS", entries, images=(PNG_URI,))
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "user"])
        last = next(m for m in reversed(messages) if m["role"] == "user")
        self.assertEqual(last.get("images"), [PNG_URI])
        # et nulle part ailleurs
        others = [m for m in messages if m is not last]
        self.assertTrue(all(m.get("images") is None for m in others))

    def test_no_images_no_key_added(self):
        self.assertEqual(build_messages("SYS", [], images=()),
                         [{"role": "system", "content": "SYS"}])


class ProviderImagesTest(unittest.TestCase):
    """Les trois fournisseurs distants reçoivent bien les images (format attendu par chacun)."""

    def test_openai_blocks(self):
        message = _openai_message({"role": "user", "content": "regarde", "images": [PNG_URI]})
        self.assertEqual(message["content"], [
            {"type": "text", "text": "regarde"},
            {"type": "image_url", "image_url": {"url": PNG_URI}},
        ])
        # pas d'image -> content plat
        self.assertEqual(_openai_message({"role": "user", "content": "salut"}),
                         {"role": "user", "content": "salut"})

    def test_anthropic_blocks(self):
        from libs.llm.remote import RemoteClient
        system, history = RemoteClient._RemoteClient__anthropic_history([
            {"role": "user", "content": "regarde", "images": [PNG_URI]},
        ])
        self.assertEqual(history, [{"role": "user", "content": [
            {"type": "text", "text": "regarde"},
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png",
                                         "data": PNG_URI.split(",", 1)[1]}},
        ]}])

    def test_gemini_blocks(self):
        from libs.llm.remote import RemoteClient
        payload = RemoteClient.__dict__["_RemoteClient__gemini_payload"](
            [{"role": "user", "content": "regarde", "images": [PNG_URI, JPEG_URI]}], None, {}, None)
        self.assertEqual(payload["contents"], [{"role": "user", "parts": [
            {"text": "regarde"},
            {"inlineData": {"mimeType": "image/png", "data": PNG_URI.split(",", 1)[1]}},
            {"inlineData": {"mimeType": "image/jpeg", "data": JPEG_URI.split(",", 1)[1]}},
        ]}])

    def test_data_uri_helper_strips_the_base64_marker(self):
        from libs.llm.remote import _data_uri
        self.assertEqual(_data_uri(PNG_URI), ("image/png", PNG_URI.split(",", 1)[1]))
        self.assertEqual(_data_uri("data:image/webp;base64,bWlk"), ("image/webp", "bWlk"))

    def test_ollama_receives_plain_base64(self):
        # Ollama (Go) décode « images » comme du base64 brut : le préfixe data: ne doit pas
        # être envoyé, sinon l'image serait corrompue par le décodage.
        from libs.llm.ollama import _to_ollama_messages
        converted = _to_ollama_messages(
            [{"role": "user", "content": "regarde", "images": [PNG_URI]}])
        self.assertEqual(converted[0]["images"], [PNG_URI.split(",", 1)[1]])
        # un message sans image conserve son contenu
        self.assertEqual(_to_ollama_messages([{"role": "user", "content": "salut"}])[0],
                         {"role": "user", "content": "salut"})


class AgentBudgetTest(unittest.TestCase):
    """Les images pèsent dans le budget du contexte (les VLM en comptent des milliers)."""

    def test_image_message_is_larger_than_text_only(self):
        base = _size({"role": "user", "content": "regarde"})
        larger = _size({"role": "user", "content": "regarde", "images": [PNG_URI]})
        self.assertGreater(larger, base)
        # pas d'images -> même taille que sans le champ
        self.assertEqual(_size({"role": "user", "content": "regarde"}), base)

    def test_fit_context_preserves_images_on_last_user_message(self):
        # Le dernier message utilisateur n'est jamais coupé, y compris ses images
        messages = [{"role": "system", "content": "S"},
                    {"role": "user", "content": "regarde cette image", "images": [PNG_URI * 10]}]
        cut = fit_context(messages, 30)
        # on ne touche au dernier user -> il garde ses images
        self.assertEqual(messages[-1].get("images"), [PNG_URI * 10])
        # le system n'est jamais coupé
        self.assertEqual(messages[0]["content"], "S")
        # cut est False ou True selon la taille : on ne l'affirme pas, juste sa nature bool
        self.assertIn(cut, (True, False))


class EndToEndImagesTest(unittest.TestCase):
    """Rosalie complète : une image reçue est montrée au modèle multimodal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.personas = self.root / "builtin"
        self.personas.mkdir(exist_ok=True)
        (self.personas / "rosalie.md").write_text("Tu es Rosalie.", encoding="utf-8")
        from libs.config import ConfigStore
        self.store = ConfigStore(self.root / "config.sqlite3", builtin_personas=self.personas)
        from libs.config import Config
        self.rosalie = Rosalie(Config.load(self.store, self.root), self.store)

    def tearDown(self):
        from asyncio import run
        run(self.rosalie.close())
        self.store.close()
        self.tmp.cleanup()

    def test_received_image_reaches_the_llm(self):
        """Rosalie.speak(images=…) : le message de la personne porte l'image pour le modèle."""

        class FakeLLM:
            def __init__(self):
                self.messages = None

            async def chat_message(self, messages, **_):
                self.messages = [dict(m) for m in messages]
                return {"content": "Une belle photo !", "tool_calls": None, "done_reason": None}

            async def chat(self, messages, **_):
                return (await self.chat_message(messages, **_)).get("content", "")

            async def close(self):
                pass

        llm = FakeLLM()
        rosalie = self.rosalie
        rosalie.llm = llm
        rosalie.interfaces["discord"] = FakeDiscord(rosalie)
        conversation = Conversation("discord", 10, "salon #général", private=True)
        person = Person("discord", 42, "ethann", "Ethann", is_owner=True,
                        permissions=frozenset({"chat"}))
        # comme receive() le fait, le message de la personne est déjà dans la mémoire
        rosalie.memory.add(conversation.key, Entry(42, "Ethann", "regarde ! [pièce jointe : photo.png]",
                                                    is_bot=False, message_id=1))
        # sans note, sans code : la réponse directe sort directement
        reply = asyncio.run(rosalie.speak(conversation, person, reply_to=1,
                                          query="regarde !", images=(PNG_URI,)))
        self.assertEqual(reply, "Une belle photo !")
        # le dernier message de la personne contient l'image, le system non
        messages = llm.messages
        self.assertEqual(messages[0]["role"], "system")
        last_user = next(m for m in reversed(messages) if m.get("role") == "user")
        self.assertEqual(last_user.get("images"), [PNG_URI])
        self.assertNotIn("images", messages[0])
        # et l'envoi a été compté par l'interface
        self.assertEqual(rosalie.interfaces["discord"].sent[-1][1], "Une belle photo !")

    def test_receive_to_llm_full_chain(self):
        """La vraie séquence : receive() -> reply() -> speak(images=…) -> le modèle voit l'image."""
        from libs.conversation.decider import Decision
        from libs.core.types import Incoming

        class FakeLLM:
            def __init__(self):
                self.messages = None

            async def chat_message(self, messages, **_):
                self.messages = [dict(m) for m in messages]
                return {"content": "C'est mignon !", "tool_calls": None, "done_reason": None}

            async def chat(self, messages, **_):
                return (await self.chat_message(messages, **_)).get("content", "")

            async def close(self):
                pass

        async def scenario():
            from unittest import mock
            llm = FakeLLM()
            rosalie = self.rosalie
            rosalie.llm = llm
            rosalie.interfaces["discord"] = FakeDiscord(rosalie)
            # décideur : la conversation est privée -> elle répond toujours, directement
            rosalie.decider.decide = mock.AsyncMock(return_value=Decision(
                reply=True, reason="private", record=True, direct=True))
            # __schedule : la vraie version crée une tâche ; on garde la référence pour l'attendre
            task_holder = []
            def schedule_sync(incoming, direct):
                task_holder.append(asyncio.ensure_future(rosalie.reply(incoming, direct)))
            rosalie._Rosalie__schedule = schedule_sync
            conversation = Conversation("discord", 12, "en DM avec ethann", private=True)
            person = Person("discord", 42, "ethann", "Ethann", is_owner=True,
                            permissions=frozenset({"chat"}))
            incoming = Incoming(conversation=conversation, author=person,
                                text="regarde !", message_id=5, images=(PNG_URI,))
            await rosalie.receive(incoming)
            if task_holder:
                await task_holder[-1]
            return llm

        llm = asyncio.run(scenario())
        # l'envoi a eu lieu (reply a appelé speak -> send)
        self.assertTrue(self.rosalie.interfaces["discord"].sent)
        self.assertEqual(self.rosalie.interfaces["discord"].sent[-1][1], "C'est mignon !")
        # et le message de la personne porte l'image
        last_user = next(m for m in reversed(llm.messages) if m.get("role") == "user")
        self.assertEqual(last_user.get("images"), [PNG_URI])

    def test_text_only_message_still_works(self):
        """Pas d'image : le flux reste intact (pas de clé images sur les messages)."""

        class FakeLLM:
            def __init__(self):
                self.messages = None

            async def chat_message(self, messages, **_):
                self.messages = [dict(m) for m in messages]
                return {"content": "Salut !", "tool_calls": None, "done_reason": None}

            async def chat(self, messages, **_):
                return (await self.chat_message(messages, **_)).get("content", "")

            async def close(self):
                pass

        llm = FakeLLM()
        rosalie = self.rosalie
        rosalie.llm = llm
        rosalie.interfaces["discord"] = FakeDiscord(rosalie)
        conversation = Conversation("discord", 11, "en DM avec ethann", private=True)
        person = Person("discord", 42, "ethann", "Ethann", is_owner=True,
                        permissions=frozenset({"chat"}))
        rosalie.memory.add(conversation.key, Entry(42, "Ethann", "salut", is_bot=False,
                                                    message_id=9))
        reply = asyncio.run(rosalie.speak(conversation, person, reply_to=2, query="salut"))
        self.assertEqual(reply, "Salut !")
        for message in llm.messages:
            self.assertNotIn("images", message)


if __name__ == "__main__":
    unittest.main()
