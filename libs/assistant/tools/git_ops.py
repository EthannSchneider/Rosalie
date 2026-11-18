"""Git : voir l'état du repo, les diffs, commit, push, pull.

Garde-fous : les commandes git sont exécutées dans le dossier du repo (config.storage_dir).
Confirmation pour commit/push/pull, pas pour status/diff/log.
"""
import subprocess
from pathlib import Path

from libs.assistant.tools.base import ToolContext, ToolError, tool


def _git(ctx: ToolContext, *args: str, confirm: bool = False) -> str:
    repo = ctx.config.storage_dir
    cmd = ["git", *args]
    try:
        result = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=30)
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            raise ToolError(f"git {args[0]} a échoué : {output[:500]}")
        return output or "(aucune sortie)"
    except subprocess.TimeoutExpired:
        raise ToolError(f"git {args[0]} a pris trop de temps")


@tool("git_status",
      "Montre l'état du repo Git : fichiers modifiés, ajoutés, supprimés.",
      {},
      required=())
async def git_status(ctx: ToolContext) -> str:
    return _git(ctx, "status", "--short")


@tool("git_diff",
      "Montre les différences entre le working tree et le dernier commit (ou entre deux commits).",
      {"commit": ("string", "Commit à comparer (optionnel, défaut = working tree vs HEAD)")},
      required=())
async def git_diff(ctx: ToolContext, commit: str = "") -> str:
    args = ["diff"]
    if commit:
        args.append(commit)
    return _git(ctx, *args)


@tool("git_log",
      "Montre l'historique des commits (les 10 derniers par défaut).",
      {"count": ("integer", "Nombre de commits à afficher (défaut 10)")},
      required=())
async def git_log(ctx: ToolContext, count: int = 10) -> str:
    return _git(ctx, "log", f"--oneline", f"-{count}")


@tool("git_commit",
      "Commit des fichiers modifiés/ajoutés avec un message.",
      {"message": ("string", "Message du commit"),
       "all": ("boolean", "true = inclure les suppressions aussi (git add -A)")},
      required=("message",),
      confirm="Commit : {message}")
async def git_commit(ctx: ToolContext, message: str, all: bool = False) -> str:
    if all:
        _git(ctx, "add", "-A")
    else:
        _git(ctx, "add", "-u")
    return _git(ctx, "commit", "-m", message)


@tool("git_push",
      "Pousse les commits locaux vers l'origine.",
      {"branch": ("string", "Nom de la branche (vide = branche courante)")},
      required=(),
      confirm="Push vers l'origine ?")
async def git_push(ctx: ToolContext, branch: str = "") -> str:
    args = ["push"]
    if branch:
        args.append(branch)
    return _git(ctx, *args)


@tool("git_pull",
      "Tire les changements de l'origine et merge.",
      {"branch": ("string", "Nom de la branche (vide = branche courante)")},
      required=(),
      confirm="Pull depuis l'origine ?")
async def git_pull(ctx: ToolContext, branch: str = "") -> str:
    args = ["pull"]
    if branch:
        args.append(branch)
    return _git(ctx, *args)
