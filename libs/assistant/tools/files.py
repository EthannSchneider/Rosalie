"""Fichiers : lire, écrire, lister, supprimer, déplacer, copier des fichiers.

Garde-fous : les chemins sont résolus dans le dossier de travail de Rosalie (storages/workspace)
ou dans le repo si le chemin est absolu. Pas de confirmation pour read/list, confirmation pour
write/delete/move/copy.
"""
import os
import shutil
from pathlib import Path

from libs.assistant.tools.base import ToolContext, ToolError, tool


def _resolve(path: str, ctx: ToolContext) -> Path:
    """Résout un chemin (relatif au dossier de travail ou absolu)."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = ctx.config.storage_dir / "workspace" / p
    return p


@tool("read_file",
      "Lit le contenu d'un fichier. Renvoie le texte complet (ou coupé si trop long).",
      {"path": ("string", "Chemin du fichier (relatif au dossier de travail ou absolu)")},
      required=("path",))
async def read_file(ctx: ToolContext, path: str) -> str:
    p = _resolve(path, ctx)
    if not p.exists():
        raise ToolError(f"fichier introuvable : {p}")
    if not p.is_file():
        raise ToolError(f"ce n'est pas un fichier : {p}")
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"fichier binaire (pas du texte) : {p}")
    if len(content) > 20000:
        return f"(fichier de {len(content)} caractères, affichage des 20000 premiers)\n{content[:20000]}"
    return content


@tool("write_file",
      "Écrit (ou écrase) un fichier avec le contenu donné. Crée les dossiers manquants.",
      {"path": ("string", "Chemin du fichier"),
       "content": ("string", "Contenu à écrire"),
       "append": ("boolean", "true = ajouter à la fin au lieu d'écraser")},
      required=("path", "content"),
      confirm="Écrire dans {path} ?")
async def write_file(ctx: ToolContext, path: str, content: str, append: bool = False) -> str:
    p = _resolve(path, ctx)
    p.parent.mkdir(parents=True, exist_ok=True)
    if append:
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"ajouté à la fin de {p} ({len(content)} caractères)"
    p.write_text(content, encoding="utf-8")
    return f"écrit dans {p} ({len(content)} caractères)"


@tool("list_files",
      "Liste les fichiers et dossiers d'un répertoire. Optionnel : filtrer par extension.",
      {"path": ("string", "Chemin du répertoire (vide = dossier de travail)"),
       "filter": ("string", "Filtrer par extension, ex : « .py » (optionnel)"),
       "recursive": ("boolean", "true = inclure les sous-dossiers")},
      required=())
async def list_files(ctx: ToolContext, path: str = "", filter: str = "", recursive: bool = False) -> str:
    base = _resolve(path or ".", ctx)
    if not base.exists():
        raise ToolError(f"dossier introuvable : {base}")
    if not base.is_dir():
        raise ToolError(f"ce n'est pas un dossier : {base}")
    
    entries = []
    if recursive:
        for p in sorted(base.rglob("*")):
            if filter and not p.name.endswith(filter):
                continue
            rel = p.relative_to(base)
            kind = "📁" if p.is_dir() else "📄"
            size = f" ({p.stat().st_size} o)" if p.is_file() else ""
            entries.append(f"{kind} {rel}{size}")
    else:
        for p in sorted(base.iterdir()):
            if filter and not p.name.endswith(filter):
                continue
            kind = "📁" if p.is_dir() else "📄"
            size = f" ({p.stat().st_size} o)" if p.is_file() else ""
            entries.append(f"{kind} {p.name}{size}")
    
    if not entries:
        return "(dossier vide)"
    return "\n".join(entries[:200]) + (f"\n… ({len(entries) - 200} autres)" if len(entries) > 200 else "")


@tool("delete_file",
      "Supprime un fichier ou un dossier (récursif si dossier).",
      {"path": ("string", "Chemin du fichier/dossier à supprimer")},
      required=("path",),
      confirm="Supprimer {path} ?")
async def delete_file(ctx: ToolContext, path: str) -> str:
    p = _resolve(path, ctx)
    if not p.exists():
        raise ToolError(f"introuvable : {p}")
    if p.is_dir():
        shutil.rmtree(p)
        return f"dossier supprimé : {p}"
    p.unlink()
    return f"fichier supprimé : {p}"


@tool("move_file",
      "Déplace (ou renomme) un fichier/dossier.",
      {"source": ("string", "Chemin d'origine"),
       "destination": ("string", "Chemin de destination")},
      required=("source", "destination"),
      confirm="Déplacer {source} vers {destination} ?")
async def move_file(ctx: ToolContext, source: str, destination: str) -> str:
    src = _resolve(source, ctx)
    dst = _resolve(destination, ctx)
    if not src.exists():
        raise ToolError(f"introuvable : {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"déplacé : {src} → {dst}"


@tool("copy_file",
      "Copie un fichier ou un dossier.",
      {"source": ("string", "Chemin d'origine"),
       "destination": ("string", "Chemin de destination")},
      required=("source", "destination"),
      confirm="Copier {source} vers {destination} ?")
async def copy_file(ctx: ToolContext, source: str, destination: str) -> str:
    src = _resolve(source, ctx)
    dst = _resolve(destination, ctx)
    if not src.exists():
        raise ToolError(f"introuvable : {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
    else:
        shutil.copy2(str(src), str(dst))
    return f"copié : {src} → {dst}"
