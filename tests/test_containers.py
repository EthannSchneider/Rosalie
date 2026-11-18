"""Conteneurs Docker : noms toujours préfixés, seuls ses conteneurs, arguments de `docker run`
construits sans rien de dangereux, outils et permission, réglages d'opencode.
Aucun Docker réel : la commande `docker` est remplacée par un faux."""
import asyncio
import unittest

from helpers import FakeRosalie, make_config, make_ctx
from libs.assistant.agent import hidden_tools
from libs.assistant.tools import TOOLS, execute, schemas
from libs.assistant.tools.containers import CONTAINER_TOOLS
from libs.containers import ContainerError, Docker, Spec, full_name, parse_env, parse_ports
from libs.core.types import Person
from libs.evolve.opencode import container_url, parse_result, settings


class FakeCLI:
    """Fausse commande docker : garde les appels, simule des conteneurs (nom -> étiquettes)."""
    def __init__(self):
        self.calls: list[list[str]] = []
        self.envs: list[dict] = []
        self.containers: dict[str, dict] = {}

    async def __call__(self, argv, *, env=None, stdin=None, timeout=60, on_line=None):
        self.calls.append(list(argv))
        self.envs.append(dict(env or {}))
        command, args = argv[1], argv[2:]
        if command == "version":
            return 0, "28.0", False
        if command == "inspect":
            container = self.containers.get(args[-1])
            if container is None:
                return 1, "No such container", False
            import json
            return 0, f"{json.dumps(container['labels'])}\t{container['status']}\t{container['image']}", False
        if command == "run":
            name = args[args.index("--name") + 1]
            labels = dict(a.split("=", 1) for a in (args[i + 1] for i, x in enumerate(args) if x == "--label"))
            self.containers[name] = {"labels": labels, "status": "running", "image": "img"}
            return 0, "abc", False
        if command == "ps":
            wanted = [a.removeprefix("label=").split("=", 1) for a in args if a.startswith("label=")]
            return 0, "\n".join(f"{name}\t{c['image']}\tUp\t" for name, c in self.containers.items()
                                if all(c["labels"].get(k) == v for k, v in wanted)), False
        if command == "rm":
            self.containers.pop(args[-1], None)
            return 0, "", False
        if command == "exec":
            return 0, "bonjour", False
        return 0, "", False

    def last(self, command: str) -> list[str]:
        return next(c for c in reversed(self.calls) if c[1] == command)


class DockerTest(unittest.TestCase):
    def setUp(self):
        self.cli = FakeCLI()
        self.docker = Docker(runner=self.cli)

    def test_names_are_always_prefixed(self):
        self.assertEqual(full_name("tests"), "rosalie-tests")
        self.assertEqual(full_name("Rosalie-Tests"), "rosalie-tests")
        for bad in ("", "-rf", "a b", "../x", "a;rm", "--privileged", "x" * 60, "a/b"):
            with self.assertRaises(ContainerError, msg=bad):
                full_name(bad)

    def test_run_arguments_are_built_here(self):
        asyncio.run(self.docker.run(Spec("web", "nginx:1.27", None, env={"API_KEY": "s3cret-value"},
                                         ports=[(8080, 80)])))
        argv = self.cli.last("run")
        self.assertEqual(argv[argv.index("--name") + 1], "rosalie-web")
        self.assertIn("rosalie.managed=true", argv)
        self.assertIn("127.0.0.1:8080:80", argv)              # jamais publié sur tout le réseau
        self.assertIn("no-new-privileges", argv)
        for flag in ("--memory", "--cpus", "--pids-limit"):
            self.assertIn(flag, argv)
        for forbidden in ("--privileged", "-v", "--volume", "--mount", "--pid", "--cap-add"):
            self.assertNotIn(forbidden, argv)
        self.assertNotIn("host", argv)
        # la valeur secrète passe par l'environnement, jamais par la ligne de commande
        self.assertNotIn("s3cret-value", " ".join(argv))
        self.assertEqual(self.cli.envs[-1], {"API_KEY": "s3cret-value"})
        with self.assertRaises(ContainerError):               # déjà là
            asyncio.run(self.docker.run(Spec("web", "nginx")))
        for image in ("--privileged", "-v/:/host", "nginx; rm -rf /", "a..b"):
            with self.assertRaises(ContainerError, msg=image):
                asyncio.run(self.docker.run(Spec("autre", image)))
        asyncio.run(self.docker.run(Spec("isole", "alpine", network=False)))
        argv = self.cli.last("run")
        self.assertEqual(argv[argv.index("--network") + 1], "none")

    def test_only_her_own_containers(self):
        # un conteneur de l'utilisateur dont le nom commence par rosalie- (Docker Compose) : intouchable
        self.cli.containers["rosalie-rosalie-1"] = {"labels": {}, "status": "running", "image": "rosalie"}
        for action in (self.docker.remove("rosalie-rosalie-1"), self.docker.exec("rosalie-rosalie-1", "id"),
                       self.docker.logs("rosalie-rosalie-1")):
            with self.assertRaises(ContainerError):
                asyncio.run(action)
        self.assertIn("rosalie-rosalie-1", self.cli.containers)
        self.assertFalse([c for c in self.cli.calls if c[1] in ("rm", "exec", "logs")])
        self.assertEqual(asyncio.run(self.docker.list()), [])
        self.assertFalse(asyncio.run(self.docker.remove("absent")))

    def test_exec_applies_the_timeout_inside(self):
        asyncio.run(self.docker.run(Spec("box", "alpine", ["sleep", "infinity"])))
        result = asyncio.run(self.docker.exec("box", "echo bonjour; rm -rf /", timeout=7))
        self.assertTrue(result.ok)
        argv = self.cli.last("exec")
        self.assertEqual(argv[2], "rosalie-box")
        self.assertEqual(argv[-1], "echo bonjour; rm -rf /")   # un seul argument : rien n'est interprété par l'hôte
        self.assertIn("timeout -s KILL 7", argv[-2])

    def test_ports_and_env(self):
        self.assertEqual(parse_ports("8080:80, 5432"), [(8080, 80), (5432, 5432)])
        for bad in ("80:80", "0.0.0.0:8080:80", "abc", "70000:80"):
            with self.assertRaises(ContainerError, msg=bad):
                parse_ports(bad)
        self.assertEqual(parse_env("A=1, B=x=y"), {"A": "1", "B": "x=y"})
        with self.assertRaises(ContainerError):
            parse_env("--privileged")


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.cli = FakeCLI()
        self.rosalie = FakeRosalie(make_config(containers=True, containers_max=2))
        self.rosalie.docker = Docker(runner=self.cli)
        self.ctx = make_ctx(self.rosalie)

    def run_tool(self, tool, **arguments) -> str:
        return asyncio.run(execute(self.ctx, tool, arguments))

    def test_run_exec_list_remove(self):
        self.assertIn("rosalie-tests démarré", self.run_tool("container_run", name="tests"))
        argv = self.cli.last("run")
        self.assertEqual(argv[-3:], ["python:3.13-slim", "sleep", "infinity"])   # image par défaut, en attente
        self.assertIn("bonjour", self.run_tool("container_exec", name="tests", command="echo bonjour"))
        self.assertIn("rosalie-tests", self.run_tool("container_list"))
        self.assertEqual(self.rosalie.interfaces["test"].confirms, [])           # aucune confirmation
        self.assertIn("supprimé", self.run_tool("container_remove", name="tests"))
        self.assertTrue(self.run_tool("container_exec", name="tests", command="id").startswith("Erreur"))

    def test_limits_and_reserved_names(self):
        self.run_tool("container_run", name="a", image="nginx", command="image")
        self.assertEqual(self.cli.last("run")[-1], "nginx")                      # commande de l'image
        self.run_tool("container_run", name="b", command="python -m http.server")
        self.assertEqual(self.cli.last("run")[-3:], ["sh", "-c", "python -m http.server"])
        self.assertIn("maximum", self.run_tool("container_run", name="c"))
        # les conteneurs de l'évolution du code ne sont pas à elle
        self.cli.containers["rosalie-evolve-3"] = {"labels": {"rosalie.managed": "true"}, "status": "running",
                                                   "image": "x"}
        self.assertIn("réservé", self.run_tool("container_remove", name="evolve-3"))
        self.assertIn("rosalie-evolve-3", self.cli.containers)

    def test_setting_and_permission(self):
        self.assertEqual(hidden_tools(make_config(containers=False)), CONTAINER_TOOLS)
        self.assertEqual(hidden_tools(make_config(containers=True)), frozenset())
        self.rosalie.config = make_config(containers=False)
        self.assertIn("désactivés", self.run_tool("container_run", name="x"))
        self.rosalie.config = make_config(containers=True)
        names = lambda person: {s["function"]["name"] for s in schemas(person=person)}   # noqa: E731
        other = Person("web", 2, "max", "Max", is_owner=True, permissions=frozenset({"act.code", "act.memory"}))
        allowed = Person("web", 3, "lea", "Léa", is_owner=True, permissions=frozenset({"act.containers"}))
        self.assertFalse(CONTAINER_TOOLS & names(other))
        self.assertEqual(CONTAINER_TOOLS & names(allowed), CONTAINER_TOOLS)
        self.ctx.person = other
        self.assertTrue(self.run_tool("container_run", name="x").startswith("Erreur"))
        self.assertFalse([c for c in self.cli.calls if c[1] == "run"])
        self.assertFalse(any(TOOLS[name].confirm for name in CONTAINER_TOOLS))


class OpenCodeSettingsTest(unittest.TestCase):
    def test_opencode_settings(self):
        config = make_config(code_model="ollama:qwen3:8b", ollama_url="http://127.0.0.1:11434")
        model, document, env = settings(config)
        self.assertEqual((model, env), ("ollama/qwen3:8b", {}))
        self.assertEqual(document["provider"]["ollama"]["options"]["baseURL"],
                         "http://host.docker.internal:11434/v1")
        self.assertEqual(container_url("http://ollama.lan:11434"), "http://ollama.lan:11434")
        self.assertEqual(parse_result("# fix: x\n- a\n\n## Risques\nb"), ("fix: x", "- a", "b"))
        self.assertEqual(parse_result(""), ("", "", ""))
        config = make_config(providers=("ollama", "anthropic"), code_model="anthropic:claude-sonnet-5-5",
                             anthropic_api_key="sk-ant-secret-key")
        model, document, env = settings(config)
        self.assertEqual((model, env), ("anthropic/claude-sonnet-5-5", {"ANTHROPIC_API_KEY": "sk-ant-secret-key"}))
        self.assertNotIn("sk-ant", str(document))            # la clé passe par l'environnement


if __name__ == "__main__":
    unittest.main()
