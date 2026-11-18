"""Bac à sable d'une opération : un conteneur Docker « rosalie-evolve-<n> » où le modèle de code
peut lancer n'importe quelle commande (shell, tests, opencode) sans toucher à la machine.

Le clone de travail y est monté sur /workspace ; son dossier `.git` est CACHÉ (recouvert par un
dossier vide en mémoire) : rien de ce qui tourne dans le conteneur ne peut modifier la
configuration ou les hooks de git, que l'hôte utilise ensuite pour commit et push. Le jeton GitHub
n'entre jamais dans le conteneur.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Mapping, Sequence

from libs.config import ROOT_DIR
from libs.containers import KEEP_ALIVE, ContainerError, Docker, ExecResult, Limits, Spec

WORKDIR = "/workspace"
HOME = "/tmp/home"
DEFAULT_IMAGE = "rosalie-evolve:latest"
DOCKERFILE = ROOT_DIR / "deploy" / "docker" / "evolve.Dockerfile"
KIND = "evolve"
# Environnement des commandes : données à part (jamais celles de Rosalie), rien d'interactif
ENV = {"HOME": HOME, "STORAGE_DIR": f"{HOME}/storages", "LOG_FILE": "/dev/null", "LOG_QUIET": "1",
       "PYTHONDONTWRITEBYTECODE": "1", "CI": "1", "GIT_TERMINAL_PROMPT": "0",
       "PATH": f"{HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}


def container_name(operation_id: int) -> str:
    return f"rosalie-evolve-{operation_id}"


class Sandbox:
    def __init__(self, docker: Docker, root: Path, operation_id: int, *, image: str = DEFAULT_IMAGE,
                 limits: Limits = Limits(), network: bool = True,
                 on_line: Callable[[str], None] | None = None):
        self.docker = docker
        self.root = root                        # le clone (libs/evolve/workspace.py)
        self.name = container_name(operation_id)
        self.image = image
        self.limits = limits
        self.network = network
        self.__on_line = on_line                # suivi de la construction de l'image

    async def start(self):
        problem = await self.docker.problem()
        if problem:
            raise ContainerError(problem)
        await self.__ensure_image()
        await self.docker.remove(self.name)     # reste d'une opération interrompue
        user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else ""
        await self.docker.run(Spec(
            self.name, self.image, KEEP_ALIVE, env=ENV, network=self.network, limits=self.limits,
            kind=KIND, workdir=WORKDIR, user=user, mounts=[(self.root, WORKDIR)],
            tmpfs=[f"{WORKDIR}/.git"], host_gateway=True))

    async def __ensure_image(self):
        if await self.docker.has_image(self.image):
            return
        if self.image != DEFAULT_IMAGE:
            return                              # docker run la téléchargera
        if not DOCKERFILE.is_file():
            raise ContainerError(f"l'image {DEFAULT_IMAGE} n'existe pas et {DOCKERFILE.name} est introuvable : "
                                 "construis-la à la main ou choisis une autre image (réglage evolve_image)")
        context = Path(tempfile.mkdtemp(prefix="rosalie-evolve-image-"))
        try:   # contexte minimal : seulement les dépendances Python, jamais le dossier de Rosalie
            shutil.copy(ROOT_DIR / "requirements.txt", context / "requirements.txt")
            await self.docker.build(self.image, DOCKERFILE, context, on_line=self.__on_line)
        finally:
            shutil.rmtree(context, ignore_errors=True)

    async def exec(self, command: str | Sequence[str], timeout: float = 120, *,
                   env: Mapping[str, str] | None = None,
                   on_line: Callable[[str], None] | None = None) -> ExecResult:
        return await self.docker.exec(self.name, command, timeout=timeout, workdir=WORKDIR,
                                      env=env, on_line=on_line)

    async def close(self):
        try:
            await self.docker.remove(self.name)
        except ContainerError:
            pass
