"""Environnement de travail isolé d'une opération : un clone du dépôt dans un dossier temporaire
(hors du dossier de Rosalie), une branche dédiée, des outils de fichiers enfermés dans ce clone,
les vérifications, puis commit et push de la branche.

Git tourne sans la configuration de l'utilisateur (ni identité, ni signature, ni gestionnaire
d'identifiants) ; le jeton est passé par l'environnement (jamais dans la ligne de commande, ni
dans l'adresse du dépôt, ni dans .git/config).
"""
from __future__ import annotations

import asyncio
import base64
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from libs.assistant.code_runner import safe_env

GIT_NAME = "Rosalie"
GIT_EMAIL = "rosalie@shkermit.ch"
BRANCH_PREFIX = "rosalie/"
# Ce que le modèle de code ne peut ni écrire ni supprimer (lire reste permis, sauf .git)
PROTECTED = (".git", ".github", "storages")
MAX_FILE = 400_000          # caractères par fichier écrit
READ_LINES = 400            # lignes par lecture
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
    """Les vérifications du projet (AGENTS.md). Le site n'est reconstruit que s'il a changé."""
    return [
        Check("Compilation Python", [sys.executable, "-m", "compileall", "-q", "libs", "interfaces", "commands"]),
        Check("Tests unitaires (python bot.py test)", [sys.executable, "bot.py", "test"]),
        Check("Dépendances du site (npm ci)", ["npm", "--prefix", "webui", "ci", "--no-audit", "--no-fund"],
              only_if="webui/"),
        Check("Construction du site (npm run build)", ["npm", "--prefix", "webui", "run", "build"],
              only_if="webui/"),
    ]


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
    def __init__(self, remote: str, base: str, token: str = "", checks: list[Check] | None = None):
        self.remote = remote
        self.base = base
        self.__token = token
        self.checks = default_checks() if checks is None else checks
        self.home = Path(tempfile.mkdtemp(prefix="rosalie-evolve-"))   # hors du dossier de Rosalie
        self.root = self.home / "repo"
        self.base_sha = ""
        self.branch = ""

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

    # --- fichiers (outils du modèle de code) ------------------------------------------------
    def resolve(self, path: str, write: bool = False) -> Path:
        """Chemin dans le clone. Refuse d'en sortir (« .. », lien symbolique, chemin absolu),
        d'entrer dans .git, et d'écrire dans les dossiers protégés ou un fichier .env."""
        relative = Path(str(path or ".").strip())
        if relative.is_absolute():
            raise WorkspaceError("chemin relatif à la racine du dépôt attendu")
        root = self.root.resolve()
        target = (root / relative).resolve()
        if target != root and not target.is_relative_to(root):
            raise WorkspaceError(f"« {path} » sort du dépôt")
        parts = target.relative_to(root).parts
        if ".git" in parts:
            raise WorkspaceError("le dossier .git est interdit")
        if write:
            if not parts:
                raise WorkspaceError("chemin de fichier attendu")
            if parts[0] in PROTECTED or any(part == ".env" or part.startswith(".env.") for part in parts):
                raise WorkspaceError(f"« {path} » est protégé : tu ne peux pas le modifier")
        return target

    def list_files(self, path: str = ".") -> str:
        target = self.resolve(path)
        prefix = "" if target == self.root.resolve() else target.relative_to(self.root.resolve()).as_posix() + "/"
        files = [name for name in self.git("ls-files", "-co", "--exclude-standard").splitlines()
                 if name.startswith(prefix) and (self.root / name).exists()]
        if not files:
            return f"Aucun fichier dans « {path} »."
        if len(files) <= 250:
            return "\n".join(files)
        folders: dict[str, int] = {}
        for name in files:   # trop de fichiers : un niveau à la fois
            head = name[len(prefix):].split("/", 1)
            key = prefix + head[0] + ("/" if len(head) > 1 else "")
            folders[key] = folders.get(key, 0) + 1
        lines = [f"{key}  ({count} fichiers)" if key.endswith("/") else key for key, count in folders.items()]
        return f"{len(files)} fichiers ; par dossier (liste un dossier pour le détail) :\n" + "\n".join(lines)

    def read_file(self, path: str, start: int = 1, limit: int = READ_LINES) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise WorkspaceError(f"« {path} » n'existe pas (ou n'est pas un fichier)")
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            raise WorkspaceError(f"« {path} » n'est pas un fichier texte") from None
        start = max(1, start)
        limit = max(1, min(limit, READ_LINES))
        chunk = lines[start - 1:start - 1 + limit]
        text = "\n".join(f"{start + index:>5}  {line}" for index, line in enumerate(chunk))
        end = start - 1 + len(chunk)
        if end < len(lines):
            text += f"\n… ({len(lines) - end} lignes de plus : read_file avec start={end + 1})"
        return text or "(fichier vide)"

    def search(self, pattern: str, path: str = ".") -> str:
        target = self.resolve(path)
        where = "." if target == self.root.resolve() else target.relative_to(self.root.resolve()).as_posix()
        found = self.git("grep", "-n", "-I", "--untracked", "-E", "-e", pattern, "--", where, check=False)
        lines = found.splitlines()
        if not lines:
            return f"Rien trouvé pour « {pattern} »."
        shown = [line[:300] for line in lines[:80]]
        if len(lines) > 80:
            shown.append(f"… ({len(lines) - 80} autres résultats : précise la recherche ou le dossier)")
        return "\n".join(shown)

    def write_file(self, path: str, content: str) -> str:
        target = self.resolve(path, write=True)
        if len(content) > MAX_FILE:
            raise WorkspaceError(f"fichier trop gros ({len(content)} caractères, {MAX_FILE} max)")
        if target.is_dir():
            raise WorkspaceError(f"« {path} » est un dossier")
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"{'Fichier remplacé' if existed else 'Fichier créé'} : {path} ({len(content.splitlines())} lignes)."

    def replace_in_file(self, path: str, old: str, new: str) -> str:
        target = self.resolve(path, write=True)
        if not target.is_file():
            raise WorkspaceError(f"« {path} » n'existe pas")
        text = target.read_text(encoding="utf-8")
        count = text.count(old) if old else 0
        if count != 1:
            raise WorkspaceError(
                f"le texte à remplacer doit apparaître exactement une fois dans {path} "
                f"(trouvé {count} fois) : relis le fichier et donne un extrait exact, assez long pour être unique")
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"Modifié : {path}."

    def delete_file(self, path: str) -> str:
        target = self.resolve(path, write=True)
        if not target.is_file():
            raise WorkspaceError(f"« {path} » n'existe pas (ou n'est pas un fichier)")
        target.unlink()
        return f"Supprimé : {path}."

    # --- vérifications ------------------------------------------------------------------------
    async def run_checks(self, timeout: float = 900) -> list[CheckResult]:
        """Lance les vérifications dans le clone : environnement sans secrets, données dans un
        dossier temporaire à part (jamais celles de Rosalie)."""
        changed = await asyncio.to_thread(self.changed_files)
        env = safe_env()
        storage = self.home / "storages"
        storage.mkdir(exist_ok=True)
        env.update({"STORAGE_DIR": str(storage), "LOG_FILE": os.devnull, "LOG_QUIET": "1",
                    "PYTHONDONTWRITEBYTECODE": "1", "CI": "1"})
        results = []
        for check in self.checks:
            if check.only_if and not any(name.startswith(check.only_if) for name in changed):
                continue
            if shutil.which(check.command[0]) is None:
                results.append(CheckResult(check.name, None, f"{check.command[0]} introuvable : non vérifié"))
                continue
            results.append(await self.__run(check, env, timeout))
        return results

    async def __run(self, check: Check, env: dict, timeout: float) -> CheckResult:
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *check.command, cwd=self.root, env=env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout)
            ok = process.returncode == 0
            text = output.decode("utf-8", errors="replace")
        except (asyncio.TimeoutError, asyncio.CancelledError) as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)   # tout le groupe : les tests lancent des fils
            except (ProcessLookupError, PermissionError):
                pass
            await process.wait()
            if isinstance(error, asyncio.CancelledError):
                raise
            ok, text = False, f"arrêtée après {timeout:.0f} s (trop long)"
        text = text.strip()
        if len(text) > OUTPUT_TAIL:
            text = "… " + text[-OUTPUT_TAIL:]
        return CheckResult(check.name, ok, text, time.monotonic() - started)
