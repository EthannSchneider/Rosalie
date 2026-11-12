import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from libs import web
from libs.assistant import tools

JPEG = b"\xff\xd8\xff" + b"x" * 20_000
PNG = b"\x89PNG" + b"y" * 20_000


class ParseTest(unittest.TestCase):
    def test_page_image(self):
        page = ('<html><head><meta property="og:title" content="x">'
                '<meta property="og:image" content="/img/panda.jpg?a=1&amp;b=2"></head></html>')
        self.assertEqual(web.page_image(page, "https://site.org/article/"),
                         "https://site.org/img/panda.jpg?a=1&b=2")
        self.assertEqual(web.page_image('<meta content="https://x/t.png" name="twitter:image">', "https://x/"),
                         "https://x/t.png")
        self.assertIsNone(web.page_image("<html></html>", "https://x/"))

    def test_image_type(self):
        self.assertEqual(web._image_type("image/png; charset=binary", b""), "image/png")
        self.assertEqual(web._image_type("application/octet-stream", JPEG), "image/jpeg")
        self.assertEqual(web._image_type("", b"RIFF1234WEBPxx"), "image/webp")
        self.assertIsNone(web._image_type("text/html", b"<html>"))

    def test_local_images_are_refused(self):
        with self.assertRaises(web.WebError):
            asyncio.run(web.download_image("http://192.168.1.1/cam.jpg"))


class FakeChannel:
    id = 5

    def __init__(self):
        self.sent = []

    async def send(self, content=None, files=()):
        self.sent.append((content, [f.filename for f in files]))
        return SimpleNamespace(id=1, channel=self)


def make_ctx(author_id=42):
    config = SimpleNamespace(owner_ids={42}, web_access=True, web_search_provider="duckduckgo",
                             searxng_url="", brave_api_key="", web_contact="")
    channel = FakeChannel()
    ctx = tools.ToolContext(bot=SimpleNamespace(config=config, memory=None), channel=channel,
                            author=SimpleNamespace(id=author_id))
    return ctx, channel


class SendImageTest(unittest.TestCase):
    def test_sends_found_images_with_source(self):
        ctx, channel = make_ctx()
        results = [web.ImageResult("Panda", "https://a/1.jpg", "https://a/page"),
                   web.ImageResult("Logo", "https://a/logo.png", "https://a/"),
                   web.ImageResult("Panda 2", "https://b/2.png", "https://b/page")]
        downloads = {"https://a/1.jpg": web.DownloadedImage(JPEG, "image/jpeg", ""),
                     "https://a/logo.png": web.DownloadedImage(b"\x89PNG tiny", "image/png", ""),
                     "https://b/2.png": web.DownloadedImage(PNG, "image/png", "")}
        with mock.patch.object(web, "search_images", mock.AsyncMock(return_value=results)), \
                mock.patch.object(web, "download_image",
                                  mock.AsyncMock(side_effect=lambda url, **_: downloads[url])):
            result = asyncio.run(tools.execute(ctx, "send_image", {"query": "red panda", "count": 2,
                                                                   "caption": "Regarde !"}))
        self.assertIn("2 image(s) envoyée(s) ici", result)
        [(content, files)] = channel.sent
        self.assertEqual(files, ["image1.jpg", "image2.png"])   # le logo est ignoré
        self.assertIn("Regarde !", content)
        self.assertIn("<https://a/page>", content)

    def test_falls_back_to_page_images(self):
        ctx, channel = make_ctx()
        pages = [web.SearchResult("Article", "https://news/x", "")]
        download = mock.AsyncMock(return_value=web.DownloadedImage(JPEG, "image/jpeg", ""))
        with mock.patch.object(web, "search_images", mock.AsyncMock(side_effect=web.WebError("504"))), \
                mock.patch.object(web, "search", mock.AsyncMock(return_value=pages)), \
                mock.patch.object(web, "download_image", download):
            result = asyncio.run(tools.execute(ctx, "send_image", {"query": "tour eiffel"}))
        self.assertIn("1 image(s) envoyée(s)", result)
        download.assert_awaited_with("https://news/x", follow_page=True)

    def test_nothing_found(self):
        ctx, channel = make_ctx()
        with mock.patch.object(web, "search_images", mock.AsyncMock(return_value=[])), \
                mock.patch.object(web, "search", mock.AsyncMock(return_value=[])):
            result = asyncio.run(tools.execute(ctx, "send_image", {"query": "zzz"}))
        self.assertIn("Aucune image", result)
        self.assertEqual(channel.sent, [])

    def test_send_image_url_and_guests(self):
        ctx, channel = make_ctx()
        with mock.patch.object(web, "download_image",
                               mock.AsyncMock(return_value=web.DownloadedImage(PNG, "image/png", ""))):
            self.assertIn("envoyée", asyncio.run(tools.execute(ctx, "send_image_url",
                                                               {"url": "https://x/a.png"})))
        guest, _ = make_ctx(author_id=99)
        self.assertIn("créateur", asyncio.run(tools.execute(guest, "send_image", {"query": "x"})))
        names = {s["function"]["name"] for s in tools.schemas(guest=True)}
        self.assertNotIn("send_image", names)
        self.assertNotIn("send_image", {s["function"]["name"] for s in tools.schemas(web_access=False)})


if __name__ == "__main__":
    unittest.main()
