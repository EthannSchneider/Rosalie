"""Site web : comptes et sessions, droits par rôle, réglages, chat (temps réel, confirmations,
fichiers). Le serveur tourne en local sur un port libre ; Rosalie est remplacée par un écho."""
import asyncio
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from libs.config import Config, ConfigStore, WebUIOptions
from libs.config.schema import SettingError
from libs.core.types import OutgoingFile
from libs.webui import WebServer
from libs.models.accounts import Accounts
from libs.models.user import check_password, hash_password


def make_store(root: Path) -> ConfigStore:
    personas = root / "builtin"   # intégrées ; les personnalisées vont dans root/personas
    personas.mkdir(exist_ok=True)
    (personas / "rosalie.md").write_text("Tu es Rosalie.", encoding="utf-8")
    return ConfigStore(root / "config.sqlite3", builtin_personas=personas)


class Client:
    """Un navigateur minimal : garde son cookie de session."""

    def __init__(self, url: str):
        self.url = url
        self.cookie = ""

    def request(self, method, path, body=None, headers=None):
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        if self.cookie:
            all_headers["Cookie"] = self.cookie
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method, headers=all_headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                cookie = response.headers.get("Set-Cookie")
                if cookie:
                    self.cookie = cookie.split(";")[0]
                raw = response.read().decode()
                return response.status, (json.loads(raw) if path.startswith("/api") else raw)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())


class MigrationsTest(unittest.TestCase):
    def test_fresh_database_is_at_head(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            Accounts(Path(tmp) / "rosalie.sqlite3").close()
            db = sqlite3.connect(Path(tmp) / "rosalie.sqlite3")
            self.assertEqual(db.execute("SELECT version_num FROM alembic_version").fetchone()[0], "0002")
            columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            self.assertIn("discord_id", columns)
            schema = db.execute("SELECT sql FROM sqlite_master WHERE name = 'users'").fetchone()[0]
            self.assertIn("NOCASE", schema)          # noms de compte insensibles à la casse
            self.assertIn("AUTOINCREMENT", schema)   # un id supprimé n'est jamais réutilisé
            db.close()

    def test_database_created_before_alembic_is_upgraded(self):
        """Une base de la version sans Alembic (sans discord_id) garde ses comptes."""
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rosalie.sqlite3"
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE, password TEXT NOT NULL,
                    role TEXT NOT NULL, created REAL NOT NULL, last_login REAL);
                CREATE TABLE sessions (token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires REAL NOT NULL);
            """)
            db.execute("INSERT INTO users (username, password, role, created) VALUES (?, ?, 'superadmin', 0)",
                       ("ancien", hash_password("motdepasse")))
            db.commit()
            db.close()
            accounts = Accounts(path)
            self.assertEqual(accounts.authenticate("ancien", "motdepasse").role, "superadmin")
            accounts.set_discord(accounts.find("ancien").id, "123456789012345678")
            self.assertEqual(accounts.discord_owner_ids(), frozenset({123456789012345678}))
            accounts.close()


class MainDatabaseTest(unittest.TestCase):
    def test_old_web_database_is_renamed(self):
        from libs.models import main_database
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp)
            Accounts(storage / "web.sqlite3").create("ancien", "motdepasse", "superadmin")
            path = main_database(storage)
            self.assertEqual(path.name, "rosalie.sqlite3")
            self.assertFalse((storage / "web.sqlite3").exists())
            accounts = Accounts(path)
            self.assertIsNotNone(accounts.find("ancien"))
            accounts.close()

    def test_models_do_not_depend_on_the_website(self):
        import subprocess
        import sys
        code = ("import sys, libs.models, libs.core.rosalie; "
                "print([m for m in sys.modules if m.startswith('libs.webui')])")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "[]")


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.accounts = Accounts(Path(self.tmp.name) / "rosalie.sqlite3")

    def tearDown(self):
        self.accounts.close()
        self.tmp.cleanup()

    def test_password_hash(self):
        stored = hash_password("motdepasse")
        self.assertTrue(check_password("motdepasse", stored))
        self.assertFalse(check_password("autre", stored))
        self.assertNotIn("motdepasse", stored)

    def test_setup_needs_the_code_once(self):
        code = self.accounts.setup_code
        self.assertRegex(code, r"^[0-9A-F]{4}-[0-9A-F]{4}$")
        with self.assertRaises(SettingError):
            self.accounts.setup("0000-0000", "ethann", "motdepasse")
        admin = self.accounts.setup(code.lower(), "ethann", "motdepasse")
        self.assertEqual(admin.role, "superadmin")
        self.assertIsNone(self.accounts.setup_code)
        with self.assertRaises(SettingError):
            self.accounts.setup(code, "autre", "motdepasse")

    def test_rules(self):
        boss = self.accounts.create("boss", "motdepasse", "superadmin")
        with self.assertRaises(SettingError):
            self.accounts.create("BOSS", "motdepasse")          # insensible à la casse
        with self.assertRaises(SettingError):
            self.accounts.create("x y", "motdepasse")
        with self.assertRaises(SettingError):
            self.accounts.create("court", "1234")
        with self.assertRaises(SettingError):
            self.accounts.set_role(boss.id, "user")              # dernier superadmin
        with self.assertRaises(SettingError):
            self.accounts.delete(boss.id)
        self.assertIsNone(self.accounts.authenticate("boss", "mauvais"))
        self.assertEqual(self.accounts.authenticate("Boss", "motdepasse").id, boss.id)

    def test_sessions(self):
        user = self.accounts.create("lea", "motdepasse")
        token = self.accounts.open_session(user.id)
        other = self.accounts.open_session(user.id)
        self.assertEqual(self.accounts.session_user(token).id, user.id)
        self.accounts.set_password(user.id, "nouveaumdp", keep_session=token)
        self.assertIsNotNone(self.accounts.session_user(token))
        self.assertIsNone(self.accounts.session_user(other))   # les autres sessions sont fermées
        self.accounts.close_session(token)
        self.assertIsNone(self.accounts.session_user(token))


class UsersCommandTest(unittest.TestCase):
    def test_commands(self):
        import io
        from commands.users import main
        with tempfile.TemporaryDirectory() as tmp:
            accounts = Accounts(Path(tmp) / "rosalie.sqlite3")
            out = io.StringIO()
            ask = lambda: "motdepasse"   # noqa: E731
            self.assertEqual(main(["add", "boss", "--role", "superadmin"], accounts, out, ask), 0)
            self.assertEqual(main(["add", "lea"], accounts, out, ask), 0)
            self.assertEqual(main(["role", "lea", "admin"], accounts, out, ask), 0)
            self.assertEqual(main(["discord", "lea", "123456789012345678"], accounts, out, ask), 0)
            self.assertEqual(accounts.discord_owner_ids(), frozenset({123456789012345678}))
            main(["discord", "lea", "-"], accounts, out, ask)
            self.assertEqual(accounts.discord_owner_ids(), frozenset())
            main([], accounts, out, ask)
            self.assertIn("lea", out.getvalue())
            self.assertEqual(accounts.find("lea").role, "admin")
            self.assertIsNone(accounts.setup_code)
            with self.assertRaises(SettingError):
                main(["delete", "boss"], accounts, out, ask)   # dernier superadmin
            accounts.close()


class SiteCase(unittest.TestCase):
    """Le site sans chat (comme `python bot.py web`)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = make_store(self.root)
        dist = self.root / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<h1>site</h1>")
        self.panel = WebServer(self.store, "127.0.0.1", 0, storage=self.root, dist=dist).start()
        self.boss = Client(self.panel.url)
        code = self.panel.accounts.setup_code
        status, _ = self.boss.request("POST", "/api/v1/session/setup",
                                      {"code": code, "username": "boss", "password": "motdepasse"})
        self.assertEqual(status, 200)

    def tearDown(self):
        self.panel.stop()
        self.store.close()
        self.tmp.cleanup()

    def login(self, username, password="motdepasse") -> Client:
        client = Client(self.panel.url)
        status, _ = client.request("POST", "/api/v1/session/login", {"username": username, "password": password})
        self.assertEqual(status, 200)
        return client


class SiteTest(SiteCase):
    def test_session_and_roles(self):
        anonymous = Client(self.panel.url)
        self.assertEqual(anonymous.request("GET", "/api/v1/session")[1]["user"], None)
        self.assertEqual(anonymous.request("GET", "/api/v1/settings")[0], 401)
        self.assertEqual(self.boss.request("GET", "/api/v1/session")[1]["user"]["role"], "superadmin")

        self.boss.request("POST", "/api/v1/users", {"username": "lea", "password": "motdepasse", "role": "user"})
        self.boss.request("POST", "/api/v1/users", {"username": "max", "password": "motdepasse", "role": "admin"})
        lea, admin = self.login("lea"), self.login("max")
        self.assertEqual(lea.request("GET", "/api/v1/settings")[0], 403)
        self.assertEqual(admin.request("GET", "/api/v1/settings")[0], 403)    # réglages : superadmin
        self.assertEqual(admin.request("GET", "/api/v1/users")[0], 403)
        self.assertEqual(lea.request("GET", "/api/v1/chat/messages")[0], 503)   # pas de chat ici

        users = self.boss.request("GET", "/api/v1/users")[1]["users"]
        lea_id = next(u["id"] for u in users if u["username"] == "lea")
        self.boss.request("DELETE", f"/api/v1/users/{lea_id}")
        self.assertEqual(lea.request("GET", "/api/v1/session")[1]["user"], None)

        self.assertEqual(self.boss.request("POST", "/api/v1/session/logout", {})[0], 200)
        self.assertEqual(self.boss.request("GET", "/api/v1/settings")[0], 401)

    def test_discord_link(self):
        accounts = self.panel.accounts
        self.assertEqual(self.boss.request("PUT", "/api/v1/account/discord", {"discord_id": "12"})[0], 400)
        status, session = self.boss.request("PUT", "/api/v1/account/discord",
                                            {"discord_id": "123456789012345678"})
        self.assertEqual((status, session["user"]["discord_id"]), (200, "123456789012345678"))
        self.assertEqual(accounts.discord_owner_ids(), frozenset({123456789012345678}))
        self.boss.request("POST", "/api/v1/users", {"username": "lea", "password": "motdepasse",
                                                 "role": "user", "discord_id": "223456789012345678"})
        self.assertEqual(accounts.discord_owner_ids(), frozenset({123456789012345678}))   # user : invitée
        status, result = self.login("lea").request("PUT", "/api/v1/account/discord",
                                                   {"discord_id": "123456789012345678"})
        self.assertEqual(status, 400)
        self.assertIn("boss", result["error"])                                         # déjà pris
        lea = accounts.find("lea")
        self.boss.request("PATCH", f"/api/v1/users/{lea.id}", {"role": "admin"})
        self.assertEqual(accounts.discord_owner_ids(), frozenset({123456789012345678, 223456789012345678}))
        self.boss.request("PATCH", f"/api/v1/users/{lea.id}", {"discord_id": None})
        self.assertIsNone(accounts.get(lea.id).discord_id)

    def test_legacy_owners_suggested_until_linked(self):
        from libs.config import _remember_legacy_owners
        _remember_legacy_owners(self.store, ["123456789012345678"])
        self.assertEqual(self.boss.request("GET", "/api/v1/session")[1]["legacy_owners"], ["123456789012345678"])
        self.boss.request("PUT", "/api/v1/account/discord", {"discord_id": "123456789012345678"})
        self.assertNotIn("legacy_owners", self.boss.request("GET", "/api/v1/session")[1])

    def test_wrong_passwords_are_throttled(self):
        client = Client(self.panel.url)
        statuses = [client.request("POST", "/api/v1/session/login", {"username": "boss", "password": "non"})[0]
                    for _ in range(7)]
        self.assertEqual(statuses[0], 401)
        self.assertIn(429, statuses)

    def test_change_password(self):
        self.assertEqual(self.boss.request("PUT", "/api/v1/account/password",
                                           {"current": "faux", "password": "nouveaumdp"})[0], 400)
        self.assertEqual(self.boss.request("PUT", "/api/v1/account/password",
                                           {"current": "motdepasse", "password": "nouveaumdp"})[0], 200)
        self.assertEqual(self.boss.request("GET", "/api/v1/settings")[0], 200)   # session gardée
        self.login("boss", "nouveaumdp")

    def test_settings_hide_secrets(self):
        self.store.set("discord_token", "abc.def")
        status, state = self.boss.request("GET", "/api/v1/settings")
        self.assertEqual(status, 200)
        token = next(f for f in state["fields"] if f["key"] == "discord_token")
        self.assertTrue(token["is_set"])
        self.assertNotIn("abc.def", json.dumps(state))
        status, result = self.boss.request("PATCH", "/api/v1/settings", {"changes": {"num_ctx": 1}})
        self.assertEqual(status, 400)
        self.assertIn("minimum", result["error"])
        self.assertEqual(self.boss.request("PUT", "/api/v1/personas/pirate", {"text": "Arr.", "create": True})[0], 200)
        self.assertEqual(self.boss.request("GET", "/api/v1/personas/pirate")[1]["text"].strip(), "Arr.")

    def test_api_is_versioned(self):
        self.assertEqual(self.boss.request("GET", "/api/state")[0], 404)
        status, result = self.boss.request("GET", "/api/v2/settings")
        self.assertEqual(status, 404)
        self.assertIn("/api/v1", result["error"])
        self.assertEqual(self.boss.request("PUT", "/api/v1/settings", {})[0], 405)

    def test_cross_site_and_static(self):
        changes = {"changes": {"code_exec": False}}
        self.assertEqual(self.boss.request("PATCH", "/api/v1/settings", changes,
                                           {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.boss.request("PATCH", "/api/v1/settings", changes,
                                           {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.boss.request("GET", "/api/v1/session", headers={"Host": "evil.example"})[0], 403)
        self.assertIs(self.store.get("code_exec"), True)
        self.assertEqual(self.boss.request("GET", "/../../etc/passwd")[1], "<h1>site</h1>")


class FakeRosalie:
    """Juste ce que l'interface web utilise ; répond en écho (ou demande une confirmation)."""

    def __init__(self, root: Path, store: ConfigStore):
        self.store = store
        self.config = Config.load(store, root)
        self.accounts = Accounts(root / "rosalie.sqlite3")
        self.memory = SimpleNamespace(clear=lambda key: None)
        self.decider = SimpleNamespace(stop=lambda key: None)
        self.web = None
        self.received = []

    def typing_from(self, conversation, person):
        pass

    async def receive(self, incoming):
        self.received.append(incoming)
        conversation = incoming.conversation
        if incoming.text == "confirme":
            confirmed, _ = await self.web.confirm(conversation, "Je peux ?", code="print(1)",
                                                  language="python")
            await self.web.send(conversation, "oui" if confirmed else "non")
        elif incoming.text == "photo":
            await self.web.send(conversation, "voilà", files=[OutgoingFile("chat.png", b"\x89PNG")])
        else:
            async with self.web.typing(conversation):
                await self.web.send(conversation, f"écho : {incoming.text}", reply_to=incoming.message_id)


class ChatTest(unittest.TestCase):
    def setUp(self):
        from interfaces.web import WebInterface
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = make_store(root)
        self.rosalie = FakeRosalie(root, self.store)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.web = WebInterface(self.rosalie, WebUIOptions("127.0.0.1", 0))
        self.rosalie.web = self.web
        self.running = asyncio.run_coroutine_threadsafe(self.web.start(), self.loop)
        accounts = self.web.accounts
        accounts.create("boss", "motdepasse", "superadmin")
        self.lea = accounts.create("lea", "motdepasse", "user")
        while self.web.loop is None:
            pass
        self.client = Client(self.web.server.url)
        self.client.request("POST", "/api/v1/session/login", {"username": "boss", "password": "motdepasse"})

    def tearDown(self):
        asyncio.run_coroutine_threadsafe(self.web.stop(), self.loop).result(5)
        self.running.result(5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()
        self.rosalie.accounts.close()
        self.store.close()
        self.tmp.cleanup()

    def wait_for(self, predicate, timeout=5.0):
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(0.02)
        self.fail("délai dépassé")

    def history(self, client=None):
        return (client or self.client).request("GET", "/api/v1/chat/messages")[1]["messages"]

    def test_message_and_reply(self):
        status, result = self.client.request("POST", "/api/v1/chat/messages", {"text": "salut"})
        self.assertEqual(status, 201)
        messages = self.wait_for(lambda: len(self.history()) == 2 and self.history())
        self.assertEqual([m["text"] for m in messages], ["salut", "écho : salut"])
        self.assertEqual(messages[1]["meta"]["reply_to"], result["message"]["id"])
        incoming = self.rosalie.received[0]
        self.assertTrue(incoming.author.is_owner)
        self.assertTrue(incoming.conversation.private)
        self.assertEqual(incoming.conversation.key, f"web:{incoming.author.id}")

    def test_each_account_has_its_own_conversation(self):
        lea = Client(self.web.server.url)
        lea.request("POST", "/api/v1/session/login", {"username": "lea", "password": "motdepasse"})
        lea.request("POST", "/api/v1/chat/messages", {"text": "coucou"})
        self.wait_for(lambda: len(self.history(lea)) == 2)
        self.assertEqual(self.history(), [])
        self.assertFalse(self.rosalie.received[0].author.is_owner)   # rôle user = invité

    def test_live_events(self):
        request = urllib.request.Request(self.web.server.url + "/api/v1/chat/events",
                                         headers={"Cookie": self.client.cookie})
        stream = urllib.request.urlopen(request, timeout=5)
        self.wait_for(lambda: self.web.hub.listeners(self.web.accounts.find("boss").id))
        self.client.request("POST", "/api/v1/chat/messages", {"text": "hey"})
        events = []
        while len([e for e in events if e["type"] == "message"]) < 2:
            line = stream.readline().decode()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        stream.close()
        self.assertEqual([e["type"] for e in events], ["message", "typing", "message", "typing"][:len(events)])
        self.assertEqual(events[-1]["message"]["text"], "écho : hey")

    def test_confirmation(self):
        self.client.request("POST", "/api/v1/chat/messages", {"text": "confirme"})
        ask = self.wait_for(lambda: next((m for m in self.history() if m["kind"] == "confirm"), None))
        self.assertEqual(ask["meta"]["status"], "pending")
        self.assertEqual(ask["meta"]["code"], "print(1)")
        self.assertEqual(self.client.request("POST", f"/api/v1/chat/confirmations/{ask['id']}", {"accept": True})[0], 200)
        self.wait_for(lambda: self.history()[-1]["text"] == "oui")
        self.assertEqual(self.history()[1]["meta"]["status"], "accepted")
        self.assertEqual(self.client.request("POST", f"/api/v1/chat/confirmations/{ask['id']}", {"accept": True})[0], 400)

    def test_files_are_private(self):
        self.client.request("POST", "/api/v1/chat/messages", {"text": "photo"})
        message = self.wait_for(lambda: next((m for m in self.history() if m["meta"].get("files")), None))
        file_id = message["meta"]["files"][0]["id"]
        request = urllib.request.Request(f"{self.web.server.url}/api/v1/chat/files/{file_id}",
                                         headers={"Cookie": self.client.cookie})
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.read(), b"\x89PNG")
            self.assertEqual(response.headers["Content-Type"], "image/png")
        lea = Client(self.web.server.url)
        lea.request("POST", "/api/v1/session/login", {"username": "lea", "password": "motdepasse"})
        self.assertEqual(lea.request("GET", f"/api/v1/chat/files/{file_id}")[0], 404)

    def test_reset(self):
        self.client.request("POST", "/api/v1/chat/messages", {"text": "salut"})
        self.wait_for(lambda: len(self.history()) == 2)
        self.client.request("DELETE", "/api/v1/chat/messages")
        self.assertEqual(self.history(), [])


if __name__ == "__main__":
    unittest.main()
