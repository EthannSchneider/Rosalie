"""Évolution du code : permissions, environnement de travail, flux complet jusqu'à la pull
request (dépôt git local, faux GitHub, faux Docker où « opencode » est une fonction), reprise
après un redémarrage, fusion, mise à jour, superviseur.
Aucun réseau ni Docker : le « dépôt distant » est un dépôt git local."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import FakeRosalie, make_config, make_ctx
from libs.config.schema import SettingError
from libs.evolve import Brief, Evolver, redact
from libs.containers import ExecResult
from libs.evolve.opencode import EXIT_FILE, PROMPT_FILE, RESULT_FILE
from libs.evolve.workspace import Check, Workspace, WorkspaceError
from libs.models import Accounts
from libs.models.evolution import WORK
from libs.supervisor import Supervisor

SECRET = "ghp_" + "a1B2c3D4e5" * 3


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "T",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


def make_origin(root: Path) -> Path:
    """Un dépôt « distant » nu, avec un premier commit sur main."""
    seed = root / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    (seed / "AGENTS.md").write_text("# Conventions\nTout est en français.\n")
    (seed / "app.py").write_text("VALUE = 1\n")
    (seed / "version.txt").write_text("A")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "init")
    origin = root / "origin.git"
    git(root, "clone", "-q", "--bare", str(seed), str(origin))
    return origin


class LocalDocker:
    """Faux Docker : « le conteneur » est le dossier monté, les commandes y tournent en local, et
    opencode est remplacé par `work(root)` (qui modifie le clone et renvoie son compte rendu).
    hold=True : opencode ne termine pas tant qu'on n'appelle pas finish()."""
    def __init__(self, work=None, code: str = "0", hold: bool = False):
        self.work, self.code, self.hold = work, code, hold
        self.specs, self.commands, self.removed, self.launched = [], [], [], []
        self.files: dict[str, str] = {}
        self.running: set[str] = set()
        self.env: dict[str, str] = {}
        self.root = None

    async def problem(self):
        return ""

    async def has_image(self, image):
        return True

    async def list(self, kind=None):
        return [{"name": name} for name in self.running]

    async def managed(self, name):
        return {"name": name, "status": "running", "image": "x", "kind": "evolve"} if name in self.running else None

    async def mount_source(self, name, target):
        return self.root if name in self.running else None

    async def run(self, spec):
        self.specs.append(spec)
        self.root = spec.mounts[0][0]
        self.running.add(spec.name)
        return spec.name

    async def remove(self, name):
        self.removed.append(name)
        existed = name in self.running
        self.running.discard(name)
        return existed

    async def exec(self, name, command, *, timeout=120, workdir="", env=None, stdin=None, on_line=None):
        self.commands.append(command)
        done = subprocess.run(command, shell=isinstance(command, str), cwd=self.root, capture_output=True, text=True)
        return ExecResult((done.stdout + done.stderr).strip(), done.returncode, 0.1)

    async def exec_detached(self, name, command, *, workdir="", env=None):
        self.launched.append(list(command))
        self.env = dict(env or {})
        if not self.hold:
            self.finish()

    def finish(self):
        result = self.work(self.root) if self.work else ""
        if result:
            self.files[RESULT_FILE] = result
        self.files[EXIT_FILE] = self.code

    async def write_file(self, name, path, content):
        self.files[path] = content

    async def read_file(self, name, path, limit=20_000, tail=False):
        return self.files.get(path, "")


class FakeGitHub:
    def __init__(self):
        self.created = []
        self.merged = []
        self.state = {"merged": False, "state": "open", "merge_commit_sha": None, "base": {"ref": "main"}}

    def create_pull(self, repo, **fields):
        self.created.append({"repo": repo, **fields})
        return {"number": 7, "html_url": f"https://github.com/{repo}/pull/7"}

    def pull(self, repo, number):
        return dict(self.state)

    def merge_pull(self, repo, number, *, sha, method="squash"):
        self.merged.append((number, sha))
        self.state.update({"merged": True, "state": "closed", "merge_commit_sha": "f" * 40})
        return {"merged": True}


OK_CHECK = [Check("Vérification factice", [sys.executable, "-c", "print('tout va bien')"])]
BAD_CHECK = [Check("Tests factices", [sys.executable, "-c", "import sys; print('boum'); sys.exit(1)"])]
BRIEF = Brief("Ajouter un salut", "feature", "Ajouter une fonction hello() dans app.py.",
              context=f"Ne pas répéter ce jeton : {SECRET}", criteria="hello() renvoie « salut ».")


def add_hello(root: Path) -> str:
    """Ce que fait « opencode » : la modification demandée, un chemin protégé au passage, et
    son compte rendu."""
    (root / "app.py").write_text("VALUE = 1\n\n\ndef hello():\n    return 'salut'\n")
    (root / ".github").mkdir()
    (root / ".github" / "ci.yml").write_text("interdit")
    return "feat: add hello\n- ajoute hello()\n\n## Risques\naucun"


class EvolveCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.origin = make_origin(self.root)
        self.rosalie = FakeRosalie(make_config(evolve=True, containers=True, github_token=SECRET,
                                               storage_dir=self.root / "storages"), self.root)
        self.rosalie.accounts = Accounts(self.root / "storages" / "rosalie.sqlite3")
        self.github = FakeGitHub()

    def tearDown(self):
        self.rosalie.accounts.close()
        self.tmp.cleanup()

    def evolver(self, work=add_hello, checks=OK_CHECK, docker: LocalDocker | None = None) -> Evolver:
        self.docker = docker or LocalDocker(work)
        self.rosalie.evolver = Evolver(self.rosalie, github=self.github, remote=str(self.origin),
                                       checks=checks, docker=self.docker)
        self.rosalie.evolver.poll = 0.01
        return self.rosalie.evolver

    def run_operation(self, evolver: Evolver, brief: Brief = BRIEF):
        async def scenario():
            operation = evolver.start(brief, author="boss")
            while evolver.operations.get(operation.id).status in WORK:
                await asyncio.sleep(0.02)
            await evolver.close()
            return evolver.operations.get(operation.id)
        return asyncio.run(scenario())


class PullRequestTest(EvolveCase):
    def test_change_goes_through_a_pull_request(self):
        evolver = self.evolver()
        main_before = git(self.origin, "rev-parse", "main")
        operation = self.run_operation(evolver)

        self.assertEqual(operation.status, "pr_open", operation.error)
        self.assertEqual(operation.pr_url, "https://github.com/EthannSchneider/Rosalie/pull/7")
        self.assertTrue(operation.checks_ok)
        self.assertEqual(operation.author, "boss")
        # la branche dédiée est poussée ; la branche de référence n'a pas bougé
        self.assertTrue(operation.branch.startswith("rosalie/evolve-1-"))
        self.assertEqual(git(self.origin, "rev-parse", operation.branch), operation.head_sha)
        self.assertEqual(git(self.origin, "rev-parse", "main"), main_before)
        self.assertEqual(operation.base_sha, main_before)
        self.assertIn("def hello", git(self.origin, "show", f"{operation.branch}:app.py"))
        # la pull request explique pourquoi, quoi, les vérifications et les risques — sans secret
        pull = self.github.created[0]
        self.assertEqual((pull["head"], pull["base"], pull["draft"]), (operation.branch, "main", False))
        for part in ("## Pourquoi", "## Modifications", "## Vérifications", "## Risques et limites",
                     "Nouvelle fonctionnalité", "boss", "app.py", "✅ Vérification factice"):
            self.assertIn(part, pull["body"])
        self.assertNotIn(SECRET, pull["body"])
        self.assertNotIn(SECRET, json.dumps([e for e in operation.events]))
        self.assertEqual(pull["title"], "feat: add hello")
        self.assertIn("avec opencode", pull["body"])
        # opencode a tourné en détaché dans le conteneur, avec le modèle de code et le dossier complet
        self.assertEqual(self.docker.launched[0][-2:], ["ollama/qwen3:8b", "3600"])
        for part in ("Objectif", "Contexte", "Critères de réussite", "hello()", "AGENTS.md"):
            self.assertIn(part, self.docker.files[PROMPT_FILE])
        # le conteneur : nom préfixé, .git caché, jamais le jeton GitHub, supprimé à la fin
        spec = self.docker.specs[0]
        self.assertEqual(spec.name, "rosalie-evolve-1")
        self.assertEqual(spec.tmpfs, ["/workspace/.git"])
        self.assertNotIn(SECRET, str(spec) + str(self.docker.env) + str(self.docker.launched))
        self.assertEqual((self.docker.removed[-1], self.docker.running), ("rosalie-evolve-1", set()))
        self.assertIn(OK_CHECK[0].command, self.docker.commands)     # vérifications dans le conteneur
        # le chemin protégé touché dans le conteneur a été rétabli, et c'est dit
        self.assertNotIn(".github", git(self.origin, "ls-tree", "-r", "--name-only", operation.branch))
        self.assertIn("chemins protégés", pull["body"])
        # suivi : analyse -> modification -> tests -> pull request
        steps = [e["status"] for e in operation.events]
        self.assertEqual([s for i, s in enumerate(steps) if i == 0 or s != steps[i - 1]],
                         ["analysis", "editing", "testing", "pr_open"])

    def test_failed_check_is_reported_and_blocks_merge(self):
        evolver = self.evolver(checks=BAD_CHECK)
        operation = self.run_operation(evolver)
        self.assertEqual(operation.status, "pr_open")
        self.assertIs(operation.checks_ok, False)
        pull = self.github.created[0]
        self.assertTrue(pull["draft"])
        self.assertIn("Vérification en échec", pull["body"])
        self.assertIn("boum", pull["body"])
        with self.assertRaises(SettingError):
            asyncio.run(evolver.merge(operation.id, "boss"))
        self.assertEqual(self.github.merged, [])

    def test_nothing_is_pushed_when_the_model_fails(self):
        def leak(root: Path) -> str:
            (root / "app.py").write_text(f"TOKEN = '{SECRET}'\n")
            return "feat: x\n- oups"
        cases = {
            "aucun fichier": LocalDocker(lambda root: "feat: x\n- rien"),
            "pas terminé": LocalDocker(add_hello, code="1"),
            "evolve_timeout": LocalDocker(add_hello, code="137"),
            "secret": LocalDocker(leak),
        }
        for expected, docker in cases.items():
            operation = self.run_operation(self.evolver(docker=docker))
            self.assertEqual(operation.status, "failed", expected)
            self.assertIn(expected, operation.error)
            self.assertNotIn(SECRET, operation.error)
        self.assertEqual(self.github.created, [])
        self.assertEqual(git(self.origin, "branch", "--list", "rosalie/*"), "")

    def test_one_operation_at_a_time(self):
        evolver = self.evolver()
        evolver.operations.create(title="a", reason="bug", brief={}, author="boss", conversation=None)
        with self.assertRaises(SettingError) as raised:
            evolver.operations.create(title="b", reason="bug", brief={}, author="boss", conversation=None)
        self.assertIn("déjà en cours", str(raised.exception))

    def test_disabled_or_unconfigured(self):
        self.rosalie.config = make_config(evolve=False, storage_dir=self.root / "storages")
        evolver = Evolver(self.rosalie, remote=str(self.origin))
        self.assertEqual(len(evolver.problems()), 3)   # désactivée, pas de jeton, pas de conteneurs
        with self.assertRaises(SettingError):
            asyncio.run(self.__start(evolver))
        with self.assertRaises(SettingError):
            Brief("Titre", "pour rire", "Un objectif assez long.").validated()

    @staticmethod
    async def __start(evolver):
        return evolver.start(BRIEF, author="boss")

    def test_work_survives_a_restart(self):
        """opencode tourne dans son conteneur : Rosalie s'arrête, redémarre, et reprend le suivi."""
        docker = LocalDocker(add_hello, hold=True)

        async def first_run():
            evolver = self.evolver(docker=docker)
            operation = evolver.start(BRIEF, author="boss")
            while not docker.launched:
                await asyncio.sleep(0.01)
            await evolver.close()                       # arrêt de Rosalie pendant le travail
            return operation.id
        operation_id = asyncio.run(first_run())
        stopped = self.rosalie.evolver.operations.get(operation_id)
        self.assertIn(stopped.status, WORK)             # pas en échec
        self.assertEqual(docker.running, {"rosalie-evolve-1"})   # conteneur et clone gardés
        self.assertTrue((docker.root / "app.py").exists())

        async def second_run():
            evolver = self.evolver(docker=docker)       # nouveau processus
            resume = asyncio.create_task(evolver.resume(delay=0))
            await asyncio.sleep(0.1)
            self.assertIn(evolver.operations.get(operation_id).status, WORK)
            docker.finish()                             # opencode termine après le redémarrage
            while evolver.operations.get(operation_id).status in WORK:
                await asyncio.sleep(0.02)
            await resume
            await evolver.close()
            return evolver.operations.get(operation_id)
        operation = asyncio.run(second_run())
        self.assertEqual(operation.status, "pr_open", operation.error)
        self.assertEqual(len(docker.launched), 1)       # opencode n'a pas été relancé
        self.assertIn("def hello", git(self.origin, "show", f"{operation.branch}:app.py"))
        self.assertEqual(docker.running, set())
        self.assertFalse(docker.root.exists())          # clone supprimé à la fin
        self.assertIn("Reprise", " ".join(e["message"] for e in operation.events))

    def test_lost_container_fails_at_restart(self):
        docker = LocalDocker(add_hello, hold=True)

        async def scenario():
            evolver = self.evolver(docker=docker)
            operation = evolver.start(BRIEF, author="boss")
            while not docker.launched:
                await asyncio.sleep(0.01)
            await evolver.close()
            docker.running.clear()                      # la machine a redémarré : plus de conteneur
            evolver = self.evolver(docker=docker)
            await evolver.resume(delay=0)
            return evolver.operations.get(operation.id)
        operation = asyncio.run(scenario())
        self.assertEqual(operation.status, "failed")
        self.assertIn("redémarrage", operation.error)

    def test_merge_then_update_request(self):
        evolver = self.evolver()
        operation = self.run_operation(evolver)

        async def scenario():
            merged = await evolver.merge(operation.id, "boss")
            self.assertEqual((merged.status, merged.merged_sha), ("merged", "f" * 40))
            self.assertEqual(self.github.merged, [(7, operation.head_sha)])
            with self.assertRaises(SettingError):          # pas de superviseur : pas de mise à jour
                await evolver.request_update(operation.id, "boss")
            state = evolver.state_dir / "supervisor.json"
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({"heartbeat": time.time()}))
            updating = await evolver.request_update(operation.id, "boss")
            self.assertEqual(updating.status, "updating")
            request = json.loads((evolver.state_dir / "update-request.json").read_text())
            self.assertEqual((request["operation"], request["pull"], request["sha"], request["by"]),
                             (operation.id, 7, "f" * 40, "boss"))
            with self.assertRaises(SettingError):          # rien d'autre pendant une mise à jour
                evolver.start(BRIEF, author="boss")
            # le superviseur avance, puis termine : l'historique suit
            state.write_text(json.dumps({"heartbeat": time.time(), "update": {
                "operation": operation.id, "status": "restarting", "message": "redémarre Rosalie",
                "previous": "a" * 40}}))
            evolver.sync()
            self.assertEqual(evolver.operations.get(operation.id).status, "restarting")
            state.write_text(json.dumps({"heartbeat": time.time(), "update": {
                "operation": operation.id, "status": "done", "message": "ok", "previous": "a" * 40,
                "deployed": "f" * 40}}))
            done = evolver.sync()[0]
            self.assertEqual((done.status, done.deployed_sha, done.previous_sha),
                             ("done", "f" * 40, "a" * 40))
        asyncio.run(scenario())

    def test_update_needs_a_merged_pull_request(self):
        evolver = self.evolver()
        operation = self.run_operation(evolver)
        with self.assertRaises(SettingError) as raised:
            asyncio.run(evolver.request_update(operation.id, "boss"))
        self.assertIn("fusionnée", str(raised.exception))


class WorkspaceTest(unittest.TestCase):
    def test_protected_paths_and_reference_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(str(make_origin(Path(tmp))), "main")
            try:
                workspace.prepare("rosalie/evolve-test")
                (workspace.root / "app.py").write_text("VALUE = 2\n")
                (workspace.root / "AGENTS.md").unlink()
                for path in (".github/workflows/ci.yml", ".env", "storages/x.db", "libs/.env.local"):
                    (workspace.root / path).parent.mkdir(parents=True, exist_ok=True)
                    (workspace.root / path).write_text("x")
                self.assertEqual(len(workspace.discard_protected()), 4)
                self.assertEqual(workspace.changed_files(), ["AGENTS.md", "app.py"])
                self.assertFalse((workspace.root / ".github" / "workflows" / "ci.yml").exists())
                with self.assertRaises(WorkspaceError):   # pas de conteneur : rien ne tourne sur l'hôte
                    asyncio.run(workspace.run_checks(30))
                with self.assertRaises(WorkspaceError):   # jamais la branche de référence
                    workspace.branch = "main"
                    workspace.push()
            finally:
                workspace.cleanup()
            self.assertFalse(workspace.home.exists())

    def test_checks_run_in_the_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(str(make_origin(Path(tmp))), "main",
                                  checks=[Check("ok", ["sh", "-c", "pwd"]), Check("site", ["npm", "x"], only_if="webui/"),
                                          Check("absent", ["sh", "-c", "exit 127"]), *BAD_CHECK])
            docker = LocalDocker()
            try:
                workspace.prepare("rosalie/evolve-test")
                docker.root = workspace.root

                class Box:
                    async def exec(self, command, timeout=120):
                        return await docker.exec("x", command)
                workspace.sandbox = Box()
                results = asyncio.run(workspace.run_checks(30))
            finally:
                workspace.cleanup()
            self.assertEqual([(r.name, r.ok) for r in results],
                             [("ok", True), ("absent", None), ("Tests factices", False)])
            self.assertIn("boum", results[2].output)

    def test_redact(self):
        text = redact(f"clé {SECRET} et ghp_{'x' * 36}", [SECRET])
        self.assertNotIn(SECRET, text)
        self.assertNotIn("ghp_", text)


class PermissionTest(EvolveCase):
    def test_only_the_superadmin_role_gets_the_permission(self):
        from libs.models.role import GRANTABLE, PERMISSIONS, Role
        roles = self.rosalie.accounts.roles
        self.assertIn("evolve", PERMISSIONS)
        self.assertNotIn("evolve", GRANTABLE)
        with self.assertRaises(SettingError):
            roles.create("dev", "Dev", ["chat", "evolve"])
        with self.assertRaises(SettingError):
            roles.update("admin", permissions=["chat", "evolve"])
        self.assertNotIn("evolve", Role(name="dev", label="Dev", permissions=["evolve"]).granted)
        accounts = self.rosalie.accounts
        self.assertTrue(accounts.create("boss", "motdepasse", "superadmin").has("evolve"))
        self.assertFalse(accounts.create("max", "motdepasse", "admin").has("evolve"))

    def test_tool_is_refused_without_the_permission(self):
        from libs.assistant.tools import TOOLS, execute, schemas
        from libs.core.types import Person
        from libs.models.role import GRANTABLE
        self.evolver()
        admin = Person("web", 2, "max", "Max", is_owner=True, permissions=frozenset(GRANTABLE))
        boss = Person("web", 1, "boss", "Boss", is_owner=True,
                      permissions=frozenset(GRANTABLE) | {"evolve"})
        names = lambda person: {s["function"]["name"] for s in schemas(person=person)}   # noqa: E731
        self.assertNotIn("request_code_change", names(admin))
        self.assertIn("request_code_change", names(boss))
        ctx = make_ctx(self.rosalie)
        ctx.person = admin
        arguments = {"title": "Ajouter un salut", "reason": "feature", "objective": "Ajouter hello() dans app.py."}
        result = asyncio.run(execute(ctx, "request_code_change", arguments))
        self.assertTrue(result.startswith("Erreur"), result)
        self.assertEqual(self.rosalie.evolver.operations.recent(), [])
        # le superadmin lance sans confirmation : le garde-fou est la pull request, relue avant fusion
        self.assertIsNone(TOOLS["request_code_change"].confirm)


class ApiTest(unittest.TestCase):
    def test_routes_are_reserved_and_health_is_public(self):
        from test_web import Client, SiteCase

        class Site(SiteCase):
            def runTest(self):
                pass
        site = Site()
        site.setUp()
        try:
            site.boss.request("POST", "/api/v1/users", {"username": "max", "password": "motdepasse", "role": "admin"})
            admin = site.login("max")
            body = {"title": "Ajouter un salut", "reason": "feature", "objective": "Ajouter hello() dans app.py."}
            for method, path in (("GET", "/api/v1/evolution"), ("POST", "/api/v1/evolution"),
                                 ("POST", "/api/v1/evolution/1/merge"), ("POST", "/api/v1/evolution/1/update")):
                self.assertEqual(Client(site.panel.url).request(method, path, body)[0], 401, path)
                self.assertEqual(admin.request(method, path, body)[0], 403, path)
            self.assertEqual(site.boss.request("GET", "/api/v1/evolution")[0], 503)   # Rosalie ne tourne pas ici
            self.assertEqual(Client(site.panel.url).request("GET", "/api/v1/health"), (200, {"ok": True}))
            session = site.boss.request("GET", "/api/v1/session")[1]
            self.assertIn("evolve", session["user"]["permissions"])
            self.assertNotIn("evolve", admin.request("GET", "/api/v1/session")[1]["user"]["permissions"])
            self.assertNotIn("evolve", [p["name"] for p in site.boss.request("GET", "/api/v1/roles")[1]["permissions"]])
        finally:
            site.tearDown()


class RemoteMessagesTest(unittest.TestCase):
    def test_tool_results_are_linked_to_their_calls(self):
        from libs.llm.remote import _openai_message, _with_call_ids
        messages = _with_call_ids([
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "a", "arguments": {"x": 1}}},
                {"id": "connu", "function": {"name": "b", "arguments": "{}"}}]},
            {"role": "tool", "content": "ra", "tool_name": "a"},
            {"role": "tool", "content": "rb", "tool_name": "b", "tool_call_id": "connu"}])
        first = messages[1]["tool_calls"][0]["id"]
        self.assertEqual([m.get("tool_call_id") for m in messages[2:]], [first, "connu"])
        converted = _openai_message(messages[1])
        self.assertEqual(converted["tool_calls"][0]["function"]["arguments"], '{"x": 1}')
        self.assertEqual(_openai_message(messages[2]), {"role": "tool", "tool_call_id": first, "content": "ra"})


CHILD = ("import pathlib, sys, time\n"
         "if pathlib.Path('version.txt').read_text() == 'B':\n"
         "    pathlib.Path(sys.argv[1], 'rosalie.sqlite3').write_text('migrée')\n"
         "time.sleep(120)\n")


class SupervisorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.origin = make_origin(root)
        self.install = root / "install"
        git(root, "clone", "-q", str(self.origin), str(self.install))
        self.a = git(self.install, "rev-parse", "HEAD")
        work = root / "work"                     # la « pull request fusionnée » : un commit B sur main
        git(root, "clone", "-q", str(self.origin), str(work))
        (work / "version.txt").write_text("B")
        git(work, "commit", "-q", "-am", "B")
        git(work, "push", "-q", "origin", "main")
        self.b = git(work, "rev-parse", "HEAD")
        self.storage = root / "storages"
        self.storage.mkdir()
        (self.storage / "rosalie.sqlite3").write_text("avant")
        self.pull = {"merged": True, "merge_commit_sha": self.b, "base": {"ref": "main"}}
        self.logs = []

    def tearDown(self):
        self.supervisor.stop_child()
        self.tmp.cleanup()

    def make(self, healthy) -> Supervisor:
        self.supervisor = Supervisor(
            self.install, self.storage, command=[sys.executable, "-c", CHILD, str(self.storage)],
            remote=str(self.origin), pull_info=lambda repo, number: self.pull, healthy=healthy,
            log=self.logs.append, poll=0.05, stop_timeout=5, health_timeout=3, stable_for=0.1)
        self.supervisor.start_child()
        return self.supervisor

    def request(self, **changes) -> dict:
        request = {"id": "r1", "operation": 4, "repo": "EthannSchneider/Rosalie", "base": "main",
                   "pull": 7, "sha": self.b, "by": "boss", **changes}
        self.supervisor.state_dir.mkdir(parents=True, exist_ok=True)
        (self.supervisor.state_dir / "update-request.json").write_text(json.dumps(request))
        return self.supervisor.take_request()

    def state(self) -> dict:
        return json.loads((self.storage / "evolve" / "supervisor.json").read_text())

    def test_update_deploys_the_merged_version(self):
        supervisor = self.make(lambda: True)
        old_child = supervisor.child
        supervisor.update(self.request())
        self.assertEqual(git(self.install, "rev-parse", "HEAD"), self.b)
        update = self.state()["update"]
        self.assertEqual((update["status"], update["deployed"], update["previous"], update["operation"]),
                         ("done", self.b, self.a, 4))
        self.assertEqual(self.state()["version"], self.b)
        self.assertIsNotNone(old_child.poll())                # l'ancienne est arrêtée
        self.assertIsNone(supervisor.child.poll())            # la nouvelle tourne
        self.assertEqual(self.state()["history"][-1]["requested_by"], "boss")

    def test_rollback_when_the_new_version_does_not_start(self):
        # « en bonne santé » seulement sur l'ancienne version
        supervisor = self.make(lambda: git(self.install, "rev-parse", "HEAD") == self.a)
        supervisor.update(self.request())
        self.assertEqual(git(self.install, "rev-parse", "HEAD"), self.a)
        update = self.state()["update"]
        self.assertEqual(update["status"], "failed")
        self.assertIs(update["rolled_back"], True)
        self.assertIn("version précédente", update["message"])
        self.assertEqual((self.storage / "rosalie.sqlite3").read_text(), "avant")   # base restaurée
        self.assertIsNone(supervisor.child.poll())            # Rosalie tourne de nouveau

    def test_refused_without_touching_anything(self):
        supervisor = self.make(lambda: True)
        child = supervisor.child
        self.pull = {"merged": False, "merge_commit_sha": None, "base": {"ref": "main"}}
        supervisor.update(self.request())
        self.assertIn("n'est pas fusionnée", self.state()["update"]["message"])
        self.pull = {"merged": True, "merge_commit_sha": "c" * 40, "base": {"ref": "main"}}
        supervisor.update(self.request())                     # pas le commit de fusion de la PR
        self.assertEqual(self.state()["update"]["status"], "failed")
        self.pull = {"merged": True, "merge_commit_sha": self.b, "base": {"ref": "main"}}
        supervisor.update(self.request(repo="quelquun/autre"))
        self.assertIn("dépôt configuré", self.state()["update"]["message"])
        (self.install / "app.py").write_text("VALUE = 2  # modification locale\n")
        supervisor.update(self.request())
        self.assertIn("modifications locales", self.state()["update"]["message"])
        self.assertEqual(git(self.install, "rev-parse", "HEAD"), self.a)
        self.assertIs(supervisor.child, child)                # jamais arrêtée
        self.assertIsNone(child.poll())
        self.assertIsNone(self.request(sha="pas-un-commit"))  # demande illisible : ignorée
