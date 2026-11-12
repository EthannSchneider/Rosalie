"""Exécution du code écrit par Rosalie, après confirmation de son créateur sur Discord.

Elle écrit un bloc ```run-python … ``` (ou ```run-bash) dans sa réponse. Ce bloc est montré
à l'owner avec des boutons ; s'il confirme, le code tourne dans un sous-processus
(dossier de travail dédié, délai max, secrets du .env retirés de l'environnement)
et la sortie lui est renvoyée pour qu'elle continue.

Ça passe par le texte, pas par le function calling : ça marche même avec un modèle
qui gère mal les outils.
"""
import asyncio
import os
import platform
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_BLOCK = re.compile(
    r"```[ \t]*(?:run|exec|execute|exécuter)[-_: \t]*(python3?|py|bash|sh|shell|zsh)[^\n]*\n(.*?)```",
    re.IGNORECASE | re.DOTALL)
_SECRET = re.compile(r"(TOKEN|SECRET|PASSWORD|API_KEY|_KEY)$", re.IGNORECASE)
OUTPUT_CHARS = 3000


@dataclass
class CodeBlock:
    language: str          # python | bash
    code: str
    before: str            # texte écrit avant le bloc
    after: str             # texte écrit après le bloc


@dataclass
class CodeResult:
    output: str
    returncode: int | None
    duration: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def summary(self) -> str:
        if self.timed_out:
            status = f"⏱️ arrêté après {self.duration:.0f} s (trop long)"
        else:
            status = f"{'✅' if self.ok else '❌'} code de sortie {self.returncode}, {self.duration:.1f} s"
        return status


def extract_code(text: str) -> CodeBlock | None:
    """Premier bloc exécutable de la réponse (un ```python normal n'est jamais exécuté)."""
    match = _BLOCK.search(text or "")
    if not match:
        return None
    language = "python" if match.group(1).lower().startswith("py") else "bash"
    return CodeBlock(language, match.group(2).strip("\n"),
                     text[:match.start()].strip(), text[match.end():].strip())


def safe_env() -> dict[str, str]:
    """Environnement du sous-processus, sans les tokens et clés du .env."""
    return {key: value for key, value in os.environ.items() if not _SECRET.search(key)}


def _truncate(text: str, limit: int = OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n… ({len(text) - limit} caractères coupés) …\n{text[-half:]}"


async def run_code(block: CodeBlock, workdir: Path, timeout: float = 60) -> CodeResult:
    workdir.mkdir(parents=True, exist_ok=True)
    if block.language == "python":
        script = workdir / "_rosalie_run.py"
        command = [sys.executable, "-u", str(script)]
    else:
        script = workdir / "_rosalie_run.sh"
        command = ["/bin/bash", str(script)]
    script.write_text(block.code, encoding="utf-8")

    start = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *command, cwd=workdir, env=safe_env(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        start_new_session=True)
    chunks: list[bytes] = []

    async def read():
        while chunk := await process.stdout.read(4096):
            chunks.append(chunk)
        await process.wait()

    timed_out = False
    try:
        await asyncio.wait_for(read(), timeout)
    except asyncio.TimeoutError:
        timed_out = True   # on garde ce qui a déjà été affiché
        _kill(process)
        await process.wait()
    finally:
        script.unlink(missing_ok=True)
    text = _truncate(b"".join(chunks).decode("utf-8", errors="replace").strip())
    return CodeResult(text, process.returncode, time.monotonic() - start, timed_out)


def _kill(process: asyncio.subprocess.Process):
    try:   # tout le groupe : les sous-processus lancés par le script aussi
        os.killpg(process.pid, 9)
    except (ProcessLookupError, PermissionError, AttributeError):
        try:
            process.kill()
        except ProcessLookupError:
            pass


def result_note(result: CodeResult) -> str:
    return (f"(Note système — résultat de l'exécution : {result.summary()}.\n"
            f"Sortie :\n{result.output or '(aucune sortie)'}\n"
            "Donne maintenant ta réponse à partir de ce résultat, sans réécrire le code. "
            "Si ça a échoué et que tu sais corriger, propose un nouveau bloc run-python/run-bash.)")


REFUSED_NOTE = "(Note système — ton créateur a refusé d'exécuter ce code. Rien n'a été exécuté.)"


def environment_line(workdir: Path) -> str:
    return (f"{platform.system()} {platform.release()}, Python {platform.python_version()}, "
            f"dossier de travail {workdir}")
