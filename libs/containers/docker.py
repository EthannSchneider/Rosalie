"""Conteneurs Docker de Rosalie : un bac à sable où elle peut lancer n'importe quelle commande.

Tout passe par la commande `docker` (bibliothèque standard seulement). Règles, appliquées ici et
non par le modèle :

  - le nom d'un conteneur commence TOUJOURS par « rosalie- » (ajouté d'office) ;
  - elle ne touche qu'aux conteneurs qu'elle a créés (étiquette `rosalie.managed=true`, vérifiée
    avant chaque action) : un conteneur de l'utilisateur nommé « rosalie-… » (celui de Docker
    Compose, par exemple) est hors de portée ;
  - les arguments de `docker run` sont construits ici : jamais de `--privileged`, de réseau de
    l'hôte, de socket Docker ni de dossier de l'hôte monté à la demande du modèle. Les montages
    (`mounts`) ne servent qu'au code de Rosalie (libs/evolve : le clone de travail) ;
  - mémoire, processeurs et nombre de processus limités ; ports publiés sur 127.0.0.1 seulement ;
  - les valeurs d'environnement passent par l'environnement de la commande `docker`, jamais par
    sa ligne de commande (une clé API ne doit pas apparaître dans `ps`).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Sequence

PREFIX = "rosalie-"
LABEL = "rosalie.managed"
KIND = "rosalie.kind"
NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,47}$")
IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/:@-]{0,199}$")
ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
MEMORY = re.compile(r"^[1-9]\d{0,5}[mg]$")
OUTPUT_CHARS = 6000
KEEP_ALIVE = ["sleep", "infinity"]
DOCKER_TIMEOUT = 60             # commandes docker courtes (inspect, rm…)
START_TIMEOUT = 900             # docker run : le temps de télécharger l'image
BUILD_TIMEOUT = 1800

# (returncode, sortie, délai dépassé)
Runner = Callable[..., Awaitable[tuple[int, str, bool]]]


class ContainerError(Exception):
    """Erreur attendue (nom refusé, Docker absent, commande docker en échec) : message montré tel quel."""


@dataclass(frozen=True)
class Limits:
    memory: str = "2g"
    cpus: float = 2.0
    pids: int = 512

    @classmethod
    def of(cls, config) -> "Limits":
        return cls(getattr(config, "containers_memory", "2g"), float(getattr(config, "containers_cpus", 2.0)))


@dataclass
class ExecResult:
    output: str
    returncode: int
    duration: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def summary(self) -> str:
        if self.timed_out:
            return f"⏱️ arrêté après {self.duration:.0f} s (trop long)"
        return f"{'✅' if self.ok else '❌'} code de sortie {self.returncode}, {self.duration:.1f} s"


@dataclass
class Spec:
    """Ce qu'il faut pour créer un conteneur. `mounts`, `tmpfs`, `user`, `hosts` : réservés au
    code de Rosalie, jamais remplis à partir de ce que dit le modèle."""
    name: str
    image: str
    command: Sequence[str] | None = None          # None = commande prévue par l'image
    env: Mapping[str, str] = field(default_factory=dict)
    ports: Sequence[tuple[int, int]] = ()         # (port sur 127.0.0.1 de l'hôte, port du conteneur)
    network: bool = True
    limits: Limits = Limits()
    kind: str = "sandbox"
    workdir: str = ""
    user: str = ""
    mounts: Sequence[tuple[Path, str]] = ()       # (dossier de l'hôte, chemin dans le conteneur)
    tmpfs: Sequence[str] = ()
    host_gateway: bool = False                    # host.docker.internal (joindre Ollama sur l'hôte)


def full_name(name: str) -> str:
    """« tests » ou « rosalie-tests » -> « rosalie-tests ». Refuse tout autre caractère."""
    short = str(name or "").strip().lower().removeprefix(PREFIX)
    if not NAME.match(short):
        raise ContainerError(f"nom de conteneur invalide « {name} » : lettres minuscules, chiffres, "
                             "« - », « _ » ou « . » (48 caractères max)")
    return PREFIX + short


def check_image(image: str) -> str:
    image = str(image or "").strip()
    if not IMAGE.match(image.lower()) or ".." in image:
        raise ContainerError(f"nom d'image invalide « {image} » (ex : python:3.13-slim, node:22, nginx)")
    return image


def parse_ports(text: str) -> list[tuple[int, int]]:
    """« 8080:80, 5432 » -> [(8080, 80), (5432, 5432)]. Ports de l'hôte : 1024 et plus."""
    ports = []
    for part in re.split(r"[,\s]+", str(text or "").strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d{1,5})(?::(\d{1,5}))?", part)
        if not match:
            raise ContainerError(f"port invalide « {part} » : attendu « 8080:80 » (hôte:conteneur)")
        host, inside = int(match.group(1)), int(match.group(2) or match.group(1))
        if not 1024 <= host <= 65535 or not 1 <= inside <= 65535:
            raise ContainerError(f"port invalide « {part} » : port de l'hôte entre 1024 et 65535")
        ports.append((host, inside))
    return ports


def parse_env(text: str) -> dict[str, str]:
    """« CLE=valeur » par ligne (ou séparées par des virgules)."""
    env = {}
    for part in re.split(r"[\n,]+", str(text or "")):
        if not part.strip():
            continue
        key, sep, value = part.strip().partition("=")
        if not sep or not ENV_KEY.match(key):
            raise ContainerError(f"variable d'environnement invalide « {part.strip()[:60]} » : attendu CLE=valeur")
        env[key] = value
    return env


def truncate(text: str, limit: int = OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n… ({len(text) - limit} caractères coupés) …\n{text[-half:]}"


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def plain(text: str) -> str:
    """Sans les codes de couleur du terminal."""
    return _ANSI.sub("", text)


async def _subprocess(argv: Sequence[str], *, env: Mapping[str, str] | None = None, stdin: bytes | None = None,
                      timeout: float = DOCKER_TIMEOUT, on_line: Callable[[str], None] | None = None,
                      keep: int = 200_000) -> tuple[int, str, bool]:
    """Lance une commande et renvoie (code, sortie, délai dépassé). La sortie gardée est bornée
    (début et fin) : une commande bavarde ne remplit pas la mémoire."""
    try:
        process = await asyncio.create_subprocess_exec(
            *argv, env={**os.environ, **(env or {})},
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    except FileNotFoundError:
        raise ContainerError("la commande « docker » est introuvable sur cette machine") from None
    head, tail = bytearray(), bytearray()

    async def pump():
        if stdin is not None:
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
        while chunk := await process.stdout.read(8192):
            room = keep - len(head)
            head.extend(chunk[:max(0, room)])
            tail.extend(chunk[max(0, room):])
            if len(tail) > keep:
                del tail[:len(tail) - keep]
            if on_line:
                lines = [line.strip() for line in plain(chunk.decode("utf-8", "replace")).splitlines()]
                if last := next((line for line in reversed(lines) if line), ""):
                    on_line(last)
        await process.wait()

    timed_out = False
    try:
        await asyncio.wait_for(pump(), timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError) as error:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()
        if isinstance(error, asyncio.CancelledError):
            raise
        timed_out = True
    text = head.decode("utf-8", "replace")
    if tail:
        text += "\n… (sortie coupée) …\n" + tail.decode("utf-8", "replace")
    return (process.returncode if process.returncode is not None else -1), plain(text).strip(), timed_out


class Docker:
    def __init__(self, binary: str = "docker", runner: Runner | None = None):
        self.binary = binary
        self.__run: Runner = runner or _subprocess

    async def __docker(self, *args: str, check: bool = True, **options) -> tuple[int, str, bool]:
        code, output, timed_out = await self.__run([self.binary, *args], **options)
        if check and (code != 0 or timed_out):
            detail = "trop long" if timed_out else (output[-600:] or f"code {code}")
            raise ContainerError(f"docker {args[0]} a échoué : {detail}")
        return code, output, timed_out

    async def problem(self) -> str:
        """Ce qui empêche d'utiliser Docker (vide = prêt)."""
        if self.__run is _subprocess and shutil.which(self.binary) is None:
            return "Docker n'est pas installé sur cette machine (commande « docker » introuvable)"
        try:
            code, output, timed_out = await self.__docker("version", "--format", "{{.Server.Version}}",
                                                          check=False, timeout=15)
        except ContainerError as error:
            return str(error)
        if code != 0 or timed_out:
            return "Docker ne répond pas (le service est-il lancé ?)"
        return ""

    # --- conteneurs ---------------------------------------------------------------------------
    async def managed(self, name: str) -> dict | None:
        """État d'un conteneur créé par Rosalie ; None s'il n'existe pas. Refuse (ContainerError)
        un conteneur du même nom qu'elle n'a pas créé."""
        name = full_name(name)
        code, output, _ = await self.__docker(
            "inspect", "--type", "container", "--format",
            '{{json .Config.Labels}}\t{{.State.Status}}\t{{.Config.Image}}', name, check=False)
        if code != 0:
            return None
        labels, _, rest = output.partition("\t")
        status, _, image = rest.partition("\t")
        try:
            labels = json.loads(labels) or {}
        except ValueError:
            labels = {}
        if labels.get(LABEL) != "true":
            raise ContainerError(f"le conteneur {name} existe mais je ne l'ai pas créé : je n'y touche pas")
        return {"name": name, "status": status.strip(), "image": image.strip(), "kind": labels.get(KIND, "")}

    async def __require(self, name: str, running: bool = False) -> dict:
        state = await self.managed(name)
        if state is None:
            raise ContainerError(f"le conteneur {full_name(name)} n'existe pas (container_list pour voir les miens)")
        if running and state["status"] != "running":
            raise ContainerError(f"le conteneur {state['name']} ne tourne pas (état : {state['status']}) ; "
                                 "regarde ses journaux, ou supprime-le et relance-le")
        return state

    async def list(self, kind: str | None = None) -> list[dict]:
        filters = ["--filter", f"label={LABEL}=true"]
        if kind:
            filters += ["--filter", f"label={KIND}={kind}"]
        _, output, _ = await self.__docker("ps", "-a", *filters, "--format",
                                           "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}")
        rows = []
        for line in output.splitlines():
            parts = (line.split("\t") + ["", "", ""])[:4]
            if parts[0].startswith(PREFIX):
                rows.append(dict(zip(("name", "image", "status", "ports"), parts)))
        return rows

    async def run(self, spec: Spec) -> str:
        """Crée et démarre un conteneur (détaché). Retourne son nom complet."""
        name = full_name(spec.name)
        image = check_image(spec.image)
        if not MEMORY.match(spec.limits.memory):
            raise ContainerError(f"limite de mémoire invalide « {spec.limits.memory} » (ex : 512m, 2g)")
        if await self.managed(name) is not None:
            raise ContainerError(f"le conteneur {name} existe déjà : utilise-le, ou supprime-le d'abord")
        args = ["run", "-d", "--name", name, "--hostname", name.removeprefix(PREFIX)[:60],
                "--label", f"{LABEL}=true", "--label", f"{KIND}={spec.kind}",
                "--init", "--security-opt", "no-new-privileges",
                "--memory", spec.limits.memory, "--cpus", f"{spec.limits.cpus:g}",
                "--pids-limit", str(spec.limits.pids)]
        if not spec.network:
            args += ["--network", "none"]
        elif spec.host_gateway:
            args += ["--add-host", "host.docker.internal:host-gateway"]
        for host, inside in spec.ports:
            args += ["-p", f"127.0.0.1:{int(host)}:{int(inside)}"]
        for key in spec.env:
            if not ENV_KEY.match(key):
                raise ContainerError(f"variable d'environnement invalide « {key} »")
            args += ["-e", key]            # la valeur vient de l'environnement de la commande docker
        for source, target in spec.mounts:
            args += ["--mount", f"type=bind,source={Path(source).resolve()},target={target}"]
        for target in spec.tmpfs:
            args += ["--tmpfs", f"{target}:exec,mode=1777"]
        if spec.workdir:
            args += ["--workdir", spec.workdir]
        if spec.user:
            args += ["--user", spec.user]
        args.append(image)
        args += list(spec.command or [])
        await self.__docker(*args, env=dict(spec.env), timeout=START_TIMEOUT)
        return name

    async def exec(self, name: str, command: str | Sequence[str], *, timeout: float = 120,
                   workdir: str = "", env: Mapping[str, str] | None = None, stdin: bytes | None = None,
                   on_line: Callable[[str], None] | None = None) -> ExecResult:
        """Lance une commande dans un conteneur qui tourne. Un texte passe par `sh -c` ; une
        liste est lancée telle quelle. Le délai est appliqué DANS le conteneur (commande
        `timeout`, si l'image l'a) : tuer `docker exec` ne tuerait pas le processus."""
        state = await self.__require(name, running=True)
        seconds = max(1, int(timeout))
        if isinstance(command, str):
            wrapper = ("if command -v timeout >/dev/null 2>&1; then exec timeout -s KILL "
                       f"{seconds} sh -c \"$0\"; else exec sh -c \"$0\"; fi")
            argv = ["sh", "-c", wrapper, command]
        else:
            argv = ["timeout", "-s", "KILL", str(seconds), *command]
        args = ["exec"]
        if stdin is not None:
            args.append("-i")
        if workdir:
            args += ["--workdir", workdir]
        for key in env or {}:
            if not ENV_KEY.match(key):
                raise ContainerError(f"variable d'environnement invalide « {key} »")
            args += ["-e", key]
        started = time.monotonic()
        code, output, timed_out = await self.__docker(
            *args, state["name"], *argv, check=False, env=dict(env or {}), stdin=stdin,
            timeout=seconds + 15, on_line=on_line)
        return ExecResult(output, code, time.monotonic() - started, timed_out or code == 137)

    async def write_file(self, name: str, path: str, content: str):
        """Écrit un fichier texte dans le conteneur (contenu passé par l'entrée standard)."""
        result = await self.exec(name, f"mkdir -p \"$(dirname {shlex.quote(path)})\" && cat > {shlex.quote(path)}",
                                 stdin=content.encode("utf-8"), timeout=30)
        if not result.ok:
            raise ContainerError(f"écriture de {path} impossible : {result.output[-300:]}")

    async def read_file(self, name: str, path: str, limit: int = 20_000, tail: bool = False) -> str:
        """Contenu d'un fichier du conteneur (« » s'il n'existe pas). tail=True : seulement la fin."""
        command = ["tail", "-c", str(limit), path] if tail else ["cat", path]
        result = await self.exec(name, command, timeout=30)
        return result.output[:limit] if result.ok else ""

    async def exec_detached(self, name: str, command: Sequence[str], *, workdir: str = "",
                            env: Mapping[str, str] | None = None):
        """Lance une commande qui continue de tourner dans le conteneur sans nous (`docker exec -d`) :
        elle survit à un redémarrage de Rosalie."""
        state = await self.__require(name, running=True)
        args = ["exec", "-d"]
        if workdir:
            args += ["--workdir", workdir]
        for key in env or {}:
            if not ENV_KEY.match(key):
                raise ContainerError(f"variable d'environnement invalide « {key} »")
            args += ["-e", key]
        await self.__docker(*args, state["name"], *command, env=dict(env or {}))

    async def mount_source(self, name: str, target: str) -> Path | None:
        """Dossier de l'hôte monté sur `target` dans un conteneur de Rosalie (None si aucun)."""
        state = await self.managed(name)
        if state is None:
            return None
        _, output, _ = await self.__docker(
            "inspect", "--type", "container", "--format",
            '{{range .Mounts}}{{.Destination}}\t{{.Source}}{{"\n"}}{{end}}', state["name"], check=False)
        for line in output.splitlines():
            destination, _, source = line.partition("\t")
            if destination.strip() == target and source.strip():
                return Path(source.strip())
        return None

    async def logs(self, name: str, tail: int = 100) -> str:
        state = await self.__require(name)
        _, output, _ = await self.__docker("logs", "--tail", str(max(1, min(int(tail), 2000))), state["name"])
        return output

    async def remove(self, name: str) -> bool:
        """Arrête et supprime un conteneur de Rosalie (et ses volumes anonymes). False s'il n'existait pas."""
        state = await self.managed(name)
        if state is None:
            return False
        await self.__docker("rm", "-f", "-v", state["name"])
        return True

    # --- images -------------------------------------------------------------------------------
    async def has_image(self, image: str) -> bool:
        code, _, _ = await self.__docker("image", "inspect", "--format", "{{.Id}}", check_image(image), check=False)
        return code == 0

    async def build(self, tag: str, dockerfile: Path, context: Path, on_line: Callable[[str], None] | None = None):
        await self.__docker("build", "-t", check_image(tag), "-f", str(dockerfile), str(context),
                            timeout=BUILD_TIMEOUT, on_line=on_line)
