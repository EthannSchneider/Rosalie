"""Environnement de travail d'une opération : un clone du dépôt dans un dossier temporaire (hors
du dossier de Rosalie), une branche dédiée, les vérifications (dans le conteneur de travail),
puis commit et push de la branche. Le modèle de code, lui, travaille dans le conteneur
(sandbox.py, opencode.py) où ce clone est monté.

Git tourne sans la configuration de l'utilisateur (ni identité, ni signature, ni gestionnaire
d'identifiants) ; le jeton est passé par l'environnement (jamais dans la ligne de commande, ni
dans l'adresse du dépôt, ni dans .git/config).
"""
from __future__ import annotations

import asyncio
import base64
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from libs.assistant.code_runner import safe_env

GIT_NAME = "Rosalie"
GIT_EMAIL = "rosalie@shkermit.ch"
BRANCH_PREFIX = "rosalie/"
# Ce que le modèle de code ne doit pas modifier : annulé avant le commit (discard_protected)
PROTECTED = (".git", ".github", "storages")
OUTPUT_TAIL = 2500          # caractères gardés de la sortie d'une vérification


class WorkspaceError(Exception):
    """Erreur attendue (chemin refusé, git en échec…) : message montré au modèle ou à l'auteur."""


@dataclass
class Check:
    name: str
    command: list[str]
    only_if: str = ""            # ne lancer que si un fichier modifié commence par ce préfixe


@dataclass
class CheckResult:
    name: str
    ok: bool | None              # None = non lancée
    output: str = ""
    duration: float = 0.0

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "output": self.output,
                "duration": round(self.duration, 1)}


def default_checks() -> list[Check]:
    """Les vérifications du projet (AGENTS.md), lancées dans le conteneur de travail. Le site n'est reconstruit que s'il a changé."""
    return [
        Check("Compilation Python", ["python", "-m", "compileall", "-q", "libs", "interfaces", "commands"]),
        Check("Tests unitaires (python bot.py test)", ["python", "bot.py", "test"]),
        Check("Dépendances du site (npm ci)", ["npm", "--prefix", "webui", "ci", "--no-audit", "--no-fund"],
              only_if="webui/"),
        Check("Construction du site (npm run build)", ["npm", "--prefix", "webui", "run", "build"],
              only_if="webui/"),
    ]


def _protected(parts: tuple[str, ...]) -> bool:
    return bool(parts) and (parts[0] in PROTECTED
                            or any(part == ".env" or part.startswith(".env.") for part in parts))


def git_env(token: str = "", remote: str = "") -> dict[str, str]:
    """Environnement de git : sans secrets, sans configuration utilisateur, jamais interactif.
    Le jeton n'est donné qu'à github.com, en en-tête HTTP."""
    env = safe_env()
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_ASKPASS": "true", "LC_ALL": "C"})
    if token and remote.startswith("https://github.com/"):
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update({"GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"})
    return env


class Workspace:
    def __init__(self, remote: str, base: str, token: str = "", checks: list[Check] | None = None,
                 home: Path | None = None):
        self.remote = remote
        self.base = base
        self.__token = token
        self.checks = default_checks() if checks is None else checks
        # hors du dossier de Rosalie ; `home` : un clone déjà là (reprise après un redémarrage)
        self.home = home or Path(tempfile.mkdtemp(prefix="rosalie-evolve-"))
        self.root = self.home / "repo"
        self.base_sha = ""
        self.branch = ""
        self.sandbox = None          # conteneur de travail (libs/evolve/sandbox.py)

    def cleanup(self):
        shutil.rmtree(self.home, ignore_errors=True)

    # --- git (bloquant : à lancer avec asyncio.to_thread) -----------------------------------
    def git(self, *args: str, auth: bool = False, check: bool = True, timeout: int = 600,
            cwd: Path | None = None) -> str:
        env = git_env(self.__token if auth else "", self.remote)
        try:
            done = subprocess.run(["git", *args], cwd=cwd or self.root, env=env, timeout=timeout,
                                  capture_output=True, text=True, errors="replace")
        except FileNotFoundError:
            raise WorkspaceError("git n'est pas installé sur cette machine") from None
        except subprocess.TimeoutExpired:
            raise WorkspaceError(f"git {args[0]} : trop long (plus de {timeout} s)") from None
        if check and done.returncode != 0:
            detail = (done.stderr or done.stdout).strip()[-600:]
            raise WorkspaceError(f"git {args[0]} a échoué : {detail}")
        return done.stdout

    def prepare(self, branch: str):
        """Clone la branche de référence (à jour) et crée la branche de travail."""
        if not branch.startswith(BRANCH_PREFIX):
            raise WorkspaceError("nom de branche de travail invalide")
        self.git("clone", "--single-branch", "--no-tags", "--branch", self.base, self.remote,
                 str(self.root), auth=True, cwd=self.home)
        self.base_sha = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-b", branch)
        self.branch = branch

    def reattach(self, branch: str, base_sha: str):
        """Reprend un clone existant (Rosalie a redémarré pendant le travail). Un commit déjà
        fait avant l'arrêt est défait (les fichiers restent) : la suite le refera proprement."""
        if not branch.startswith(BRANCH_PREFIX) or not (self.root / ".git").is_dir():
            raise WorkspaceError("le clone de travail a disparu")
        if self.git("rev-parse", "--abbrev-ref", "HEAD").strip() != branch:
            raise WorkspaceError("le clone de travail n'est pas sur la branche attendue")
        self.branch, self.base_sha = branch, base_sha
        if base_sha and self.git("rev-parse", "HEAD").strip() != base_sha:
            self.git("reset", "-q", "--soft", base_sha)

    def changed_files(self) -> list[str]:
        """Fichiers ajoutés, modifiés ou supprimés par rapport à la branche de référence."""
        self.git("add", "-A")
        return [line for line in self.git("diff", "--cached", "--name-only").splitlines() if line]

    def diff(self) -> str:
        self.git("add", "-A")
        return self.git("diff", "--cached")

    def diffstat(self) -> str:
        self.git("add", "-A")
        return self.git("diff", "--cached", "--stat").strip()

    def discard_protected(self) -> list[str]:
        """Annule toute modification d'un chemin protégé (.github, storages, .env) : dans son
        conteneur, le modèle de code peut les toucher malgré la consigne. Retourne les chemins rétablis."""
        touched = [name for name in self.changed_files() if _protected(Path(name).parts)]
        if touched:
            self.git("reset", "-q", "HEAD", "--", *touched)
            self.git("checkout", "-q", "--", *touched, check=False)    # fichiers suivis : rétablis
            self.git("clean", "-fdqx", "--", *touched, check=False)    # fichiers nouveaux : retirés
        return touched

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("-c", f"user.name={GIT_NAME}", "-c", f"user.email={GIT_EMAIL}",
                 "-c", "commit.gpgsign=false", "commit", "--no-verify", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def push(self):
        """Pousse SEULEMENT la branche de travail (jamais la branche de référence, jamais en force)."""
        if not self.branch.startswith(BRANCH_PREFIX) or self.branch == self.base:
            raise WorkspaceError("refus de pousser cette branche")
        self.git("push", "origin", f"refs/heads/{self.branch}:refs/heads/{self.branch}", auth=True)

    # --- vérifications ------------------------------------------------------------------------
    async def run_checks(self, timeout: float = 900) -> list[CheckResult]:
        """Lance les vérifications DANS le conteneur de travail : le code modifié ne tourne jamais
        sur la machine de Rosalie."""
        if self.sandbox is None:
            raise WorkspaceError("pas de conteneur de travail : vérifications impossibles")
        changed = await asyncio.to_thread(self.changed_files)
        return await self.__run_in_sandbox(changed, timeout)

    async def __run_in_sandbox(self, changed: list[str], timeout: float) -> list[CheckResult]:
        results = []
        for check in self.checks:
            if check.only_if and not any(name.startswith(check.only_if) for name in changed):
                continue
            command = list(check.command)
            done = await self.sandbox.exec(command, timeout)
            if done.returncode in (126, 127) and not done.timed_out:
                results.append(CheckResult(check.name, None, f"{command[0]} introuvable dans le conteneur : "
                                                             "non vérifié", done.duration))
                continue
            text = f"arrêtée après {timeout:.0f} s (trop long)" if done.timed_out else done.output
            if len(text) > OUTPUT_TAIL:
                text = "… " + text[-OUTPUT_TAIL:]
            results.append(CheckResult(check.name, done.ok, text, done.duration))
        return results
