"""Réglages : schéma, magasin SQLite, import de l'ancien .env, personnalités, prise en compte
à chaud, commande `settings`. Le site web est testé dans test_web.py."""
import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path

from libs.config import Config, ConfigStore, import_env
from libs.config.schema import BY_KEY, FIELDS, SettingError, find, parse
from libs.llm.persona import Persona


def make_store(root: Path) -> ConfigStore:
    personas = root / "builtin"   # intégrées ; les personnalisées vont dans root/personas
    personas.mkdir(exist_ok=True)
    (personas / "rosalie.md").write_text("Tu es Rosalie.", encoding="utf-8")
    return ConfigStore(root / "config.sqlite3", builtin_personas=personas)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = make_store(self.root)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()


class SchemaTest(unittest.TestCase):
    def test_every_field_is_a_config_attribute(self):
        attributes = set(Config.__dataclass_fields__)
        self.assertEqual([f.key for f in FIELDS if f.key not in attributes], [])

    def test_defaults_are_valid(self):
        from libs.config.schema import normalize
        for field in FIELDS:
            if field.kind not in ("persona", "tools"):
                self.assertEqual(normalize(field, field.default), field.default, field.key)

    def test_find_accepts_env_names(self):
        self.assertIs(find("OLLAMA_MODEL"), BY_KEY["ollama_model"])
        self.assertIs(find("ROSALIE_TOKEN"), BY_KEY["discord_token"])
        with self.assertRaises(SettingError):
            find("nope")

    def test_parse(self):
        self.assertIs(parse(BY_KEY["web_access"], "non"), False)
        self.assertEqual(parse(BY_KEY["num_ctx"], "8192"), 8192)
        self.assertEqual(parse(BY_KEY["channel_ids"], "123, 45 123"), ["45", "123"])
        self.assertEqual(parse(BY_KEY["names"], "rosalie, rosa"), ["rosalie", "rosa"])
        self.assertEqual(parse(BY_KEY["ollama_url"], "http://x:1/"), "http://x:1")
        for key, value in [("num_ctx", "12"), ("num_ctx", "1.5"), ("web_access", "peut-être"),
                           ("channel_ids", "abc"), ("web_browser", "parfois"), ("quiet_hours", "25-3"),
                           ("ollama_url", "ftp://x")]:
            with self.assertRaises(SettingError, msg=key):
                parse(BY_KEY[key], value)

    def test_config_conversion(self):
        config = Config.from_values({"channel_ids": ["1311111111111111111"], "decider_model": "",
                                     "ollama_model": "m", "names": ["Rosa"]}, Path("/tmp"))
        self.assertEqual(config.channel_ids, frozenset({1311111111111111111}))
        self.assertEqual(config.decider_model, "m")
        self.assertEqual(config.names, ("rosa",))
        self.assertNotIn("token", repr(config).lower())


class ConfigStoreTest(StoreCase):
    def test_defaults_and_update(self):
        self.assertEqual(self.store.get("ollama_model"), "qwen3:8b")
        self.assertEqual(self.store.update({"ollama_model": "rosalie", "num_ctx": "8192"}),
                         ["ollama_model", "num_ctx"])
        self.assertEqual(self.store.values()["num_ctx"], 8192)
        self.assertEqual(self.store.update({"ollama_model": "rosalie"}), [])
        self.store.reset("ollama_model")
        self.assertNotIn("ollama_model", self.store.overrides())

    def test_update_is_all_or_nothing(self):
        with self.assertRaises(SettingError):
            self.store.update({"ollama_model": "x", "num_ctx": 1})
        self.assertEqual(self.store.get("ollama_model"), "qwen3:8b")

    def test_unknown_tool_and_persona_refused(self):
        with self.assertRaises(SettingError):
            self.store.set("disabled_tools", ["not_a_tool"])
        self.store.set("disabled_tools", ["weather"])
        with self.assertRaises(SettingError):
            self.store.set("persona", "inconnue")

    def test_change_from_another_process_is_seen(self):
        other = ConfigStore(self.store.path, builtin_personas=self.store.builtin_dir)
        revision = self.store.revision
        self.assertFalse(self.store.refresh())
        other.set("temperature", 0.9)
        other.close()
        self.assertTrue(self.store.refresh())
        self.assertGreater(self.store.revision, revision)
        self.assertEqual(self.store.get("temperature"), 0.9)

    def test_personas(self):
        store = self.store
        self.assertEqual([(p.name, p.builtin) for p in store.personas()], [("rosalie", True)])
        for bad in [lambda: store.save_persona("rosalie", "x"), lambda: store.delete_persona("rosalie"),
                    lambda: store.save_persona("Pas Bien!", "x"), lambda: store.save_persona("vide", " ")]:
            with self.assertRaises(SettingError):
                bad()
        store.save_persona("Pirate", "Tu es une pirate.", create=True)
        with self.assertRaises(SettingError):
            store.save_persona("pirate", "doublon", create=True)
        store.set("persona", "pirate")
        store.rename_persona("pirate", "corsaire")
        self.assertEqual(store.get("persona"), "corsaire")
        self.assertEqual(store.persona_text("corsaire").strip(), "Tu es une pirate.")
        store.delete_persona("corsaire")
        self.assertEqual(store.get("persona"), "rosalie")

    def test_custom_personas_are_files_in_storage(self):
        store = self.store
        store.save_persona("pirate", "Tu es une pirate.")
        path = self.root / "personas" / "pirate.md"          # storages/personas/
        self.assertEqual(path.read_text(encoding="utf-8"), "Tu es une pirate.\n")
        self.assertFalse((store.builtin_dir / "pirate.md").exists())
        store.rename_persona("pirate", "corsaire")
        self.assertFalse(path.exists())
        self.assertTrue((self.root / "personas" / "corsaire.md").exists())
        store.delete_persona("corsaire")
        self.assertEqual(list((self.root / "personas").iterdir()), [])

    def test_hand_edited_persona_file_is_picked_up(self):
        store = self.store
        store.save_persona("pirate", "Arr.")
        revision = store.revision
        path = self.root / "personas" / "pirate.md"
        path.write_text("Arr, version longue.", encoding="utf-8")
        import os
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000))
        self.assertTrue(store.refresh())
        self.assertGreater(store.revision, revision)
        self.assertEqual(store.persona_text("pirate"), "Arr, version longue.")
        (self.root / "personas" / "Pas Valide.md").write_text("x")    # nom invalide : ignoré
        store.refresh()
        self.assertEqual([p.name for p in store.personas()], ["rosalie", "pirate"])

    def test_personas_in_database_are_moved_to_files(self):
        """Base d'avant (personas dans la table) : la migration 0002 les exporte en fichiers."""
        import sqlite3
        root = self.root / "ancienne"
        root.mkdir()
        db = sqlite3.connect(root / "config.sqlite3")
        db.executescript("""
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE personas (name TEXT PRIMARY KEY, text TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO personas VALUES ('douce', 'Tu es douce.', 0);
            INSERT INTO settings VALUES ('persona', '"douce"');
        """)
        db.commit()
        db.close()
        store = ConfigStore(root / "config.sqlite3", builtin_personas=self.store.builtin_dir)
        try:
            self.assertEqual((root / "personas" / "douce.md").read_text(encoding="utf-8"), "Tu es douce.")
            self.assertEqual(store.persona_text("douce"), "Tu es douce.")
            self.assertEqual(store.get("persona"), "douce")
            tables = {row[0] for row in sqlite3.connect(root / "config.sqlite3").execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertNotIn("personas", tables)
        finally:
            store.close()

    def test_persona_follows_settings(self):
        persona = Persona(lambda: self.store.get("persona"), self.store)
        self.assertEqual(persona.text, "Tu es Rosalie.")
        self.store.save_persona("pirate", "Arr.")
        self.store.set("persona", "pirate")
        self.assertEqual(persona.text, "Arr.")
        (self.store.builtin_dir / "rosalie.md").write_text("Nouvelle Rosalie.")
        self.store.reset("persona")
        self.assertEqual(persona.reload(), "Nouvelle Rosalie.")


class ImportEnvTest(StoreCase):
    def test_import_once(self):
        (self.root / "settings.json").write_text(json.dumps({"model": "rosalie", "initiative": False}))
        custom = self.root / "moi.md"
        custom.write_text("Persona importée")
        env = {"ROSALIE_TOKEN": "secret", "OWNER_IDS": "1, 2", "OLLAMA_MODEL": "qwen3:8b",
               "OLLAMA_NUM_CTX": "pas un nombre", "DISABLED_TOOLS": "weather",
               "PERSONA_FILE": str(custom), "QUIET_HOURS": ""}
        imported = import_env(self.store, env, self.root)
        self.assertEqual(self.store.get("discord_token"), "secret")
        from libs.config import legacy_owner_ids
        self.assertEqual(legacy_owner_ids(self.store), frozenset({1, 2}))   # plus un réglage
        self.assertEqual(self.store.get("ollama_model"), "rosalie")   # settings.json gagne
        self.assertIs(self.store.get("initiative"), False)
        self.assertEqual(self.store.get("num_ctx"), 16384)            # valeur invalide ignorée
        self.assertEqual(self.store.get("persona"), "moi")
        self.assertIn("discord_token", imported)
        self.assertEqual(import_env(self.store, {"OLLAMA_MODEL": "autre"}, self.root), [])
        self.assertEqual(import_env(self.store, {"OLLAMA_MODEL": "autre"}, self.root, force=True),
                         ["ollama_model"])

    def test_old_owner_setting_is_migrated(self):
        import os
        from unittest import mock
        from libs.config import legacy_owner_ids, load_config
        self.store.set_meta("env_imported", "1")
        import sqlite3
        db = sqlite3.connect(self.store.path)
        db.execute("INSERT INTO settings (key, value) VALUES ('owner_ids', '[\"123456789012345678\"]')")
        db.commit()
        db.close()
        with mock.patch.dict(os.environ, {"STORAGE_DIR": str(self.root)}, clear=True):
            _, store = load_config()
        self.assertEqual(legacy_owner_ids(store), frozenset({123456789012345678}))
        self.assertIsNone(store.take_legacy("owner_ids"))
        store.close()

    def test_old_interfaces_setting_is_dropped(self):
        """INTERFACES n'est plus un réglage : python bot.py lance tout sauf le terminal."""
        from interfaces import AVAILABLE, DEFAULT
        self.assertNotIn("interfaces", BY_KEY)
        self.assertEqual(set(DEFAULT), set(AVAILABLE) - {"terminal"})
        self.assertEqual(import_env(self.store, {"INTERFACES": "discord"}, self.root), [])


class DiscordOwnersTest(StoreCase):
    def test_linked_accounts_replace_old_owner_ids(self):
        from libs.config import _remember_legacy_owners
        from libs.core.rosalie import Rosalie

        async def scenario():
            rosalie = Rosalie(Config.load(self.store, self.root), self.store)
            try:
                self.assertEqual(rosalie.discord_owners(), frozenset())
                _remember_legacy_owners(self.store, ["111111111111111111"])
                self.assertEqual(rosalie.discord_owners(), frozenset({111111111111111111}))
                rosalie.accounts.create("boss", "motdepasse", "superadmin", "222222222222222222")
                self.assertEqual(rosalie.discord_owners(), frozenset({222222222222222222}))
            finally:
                await rosalie.llm.close()
                rosalie.long_term.close()
                rosalie.accounts.close()
        asyncio.run(scenario())


class SettingsCommandTest(StoreCase):
    def run_command(self, *args) -> tuple[int, str]:
        from commands.settings import main
        out = io.StringIO()
        return main(list(args), self.store, out), out.getvalue()

    def test_commands(self):
        code, text = self.run_command()
        self.assertEqual(code, 0)
        self.assertIn("ollama_model", text)
        self.assertEqual(self.run_command("set", "OLLAMA_NUM_CTX", "8192")[0], 0)
        self.assertEqual(self.store.get("num_ctx"), 8192)
        self.run_command("set", "names", "rosalie", "rosa")
        self.assertEqual(self.store.get("names"), ["rosalie", "rosa"])
        self.run_command("reset", "num_ctx")
        self.assertEqual(self.store.get("num_ctx"), 16384)
        self.assertIn("[Ollama]", self.run_command("ollama")[1])
        self.run_command("tools", "disable", "weather", "web_search")
        self.assertEqual(self.store.get("disabled_tools"), ["weather", "web_search"])
        self.run_command("tools", "enable", "weather")
        self.assertEqual(self.store.get("disabled_tools"), ["web_search"])
        self.run_command("persona", "copy", "rosalie", "rosa2")
        self.run_command("persona", "use", "rosa2")
        self.assertEqual(self.store.get("persona"), "rosa2")
        self.assertIn("* rosa2", self.run_command("persona")[1])

    def test_secret_never_displayed(self):
        self.store.set("discord_token", "abc.def")
        self.assertNotIn("abc.def", self.run_command()[1])
        self.assertNotIn("abc.def", self.run_command("get", "discord_token")[1])


if __name__ == "__main__":
    unittest.main()
