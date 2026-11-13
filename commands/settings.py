"""python bot.py settings … — voir et modifier les réglages de Rosalie depuis le terminal.

Les changements sont pris en compte à chaud si Rosalie tourne (≤ 1 s), sauf ceux marqués
« redémarrage ».
"""
from __future__ import annotations

import getpass
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from libs.config import ConfigStore, import_env, load_config, storage_dir
from libs.config.schema import FIELDS, GROUPS, SettingError, display, find, parse, tool_catalog

USAGE = """Réglages de Rosalie (storages/config.sqlite3)

  python bot.py settings                        tous les réglages
  python bot.py settings <groupe>               un groupe (ex : ollama, heartbeat)
  python bot.py settings get <clé>              une valeur et son aide
  python bot.py settings set <clé> <valeur…>    modifier (listes : a,b,c ; oui/non)
  python bot.py settings set <clé>              secret (token, clé API) : demandé sans écho
  python bot.py settings reset <clé>            revenir à la valeur par défaut

  python bot.py settings tools                  outils, activés ou non
  python bot.py settings tools disable <outil…> désactiver (enable pour réactiver)

  python bot.py settings persona                personnalités (* = active)
  python bot.py settings persona show <nom>     afficher
  python bot.py settings persona use <nom>      l'activer
  python bot.py settings persona add <nom> [fichier]    créer (depuis un fichier, ou $EDITOR)
  python bot.py settings persona edit <nom>     modifier dans $EDITOR
  python bot.py settings persona copy <source> <nom>    dupliquer (ex : partir de rosalie)
  python bot.py settings persona rename <ancien> <nouveau>
  python bot.py settings persona delete <nom>

  python bot.py settings import-env [--force]   (ré)importer les anciens réglages du .env

Les clés acceptent aussi l'ancien nom du .env (ex : OLLAMA_MODEL)."""


def run():
    store = None
    try:
        _, store = load_config(warn=False)
        sys.exit(main(sys.argv[2:], store))
    except SettingError as error:
        print(f"❌ {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        if store is not None:
            store.close()


def main(args: list[str], store: ConfigStore, out=None) -> int:
    out = out or sys.stdout

    def say(text: str = ""):
        print(text, file=out)

    if not args:
        _show(store, say, FIELDS)
        return 0
    command, rest = args[0].lower(), args[1:]
    if command in ("help", "-h", "--help"):
        say(USAGE)
    elif command == "get" and len(rest) == 1:
        field = find(rest[0])
        value = store.get(field.key)
        say(f"{field.key} = {display(field, value)}")
        say(f"  {field.label} — {field.help}" if field.help else f"  {field.label}")
        say(f"  défaut : {display(field, field.default)}"
            + ("   (redémarrage nécessaire pour l'appliquer)" if field.restart else ""))
    elif command == "set" and rest:
        field = find(rest[0])
        if len(rest) == 1:
            if field.kind != "secret":
                say(f"Valeur manquante pour {field.key}.")
                return 1
            raw = getpass.getpass(f"{field.label} (vide = effacer) : ")
            value = parse(field, raw) if raw.strip() else None
        else:
            value = parse(field, " ".join(rest[1:]) if field.kind != "list" else ",".join(rest[1:]))
        changed = store.update({field.key: value})
        _report(say, field, store.get(field.key), changed)
    elif command == "reset" and len(rest) == 1:
        field = find(rest[0])
        changed = store.reset(field.key)
        _report(say, field, store.get(field.key), changed)
    elif command == "tools":
        return _tools(store, rest, say)
    elif command in ("persona", "personas"):
        return _personas(store, rest, say)
    elif command == "import-env":
        imported = import_env(store, os.environ, storage_dir(), force="--force" in rest)
        if imported:
            say(f"Importé : {', '.join(imported)}")
        elif "--force" not in rest:
            say("Déjà importé une fois (ajoute --force pour réimporter, ça écrase les valeurs).")
        else:
            say("Rien à importer.")
    else:
        group = _group(" ".join(args))
        if group is None:
            say(USAGE)
            return 1
        _show(store, say, [field for field in FIELDS if field.group == group])
    return 0


# --- affichage -------------------------------------------------------------------------------
def _show(store: ConfigStore, say, fields):
    overrides = store.overrides()
    current = None
    for field in fields:
        if field.group != current:
            current = field.group
            say(f"\n[{current}]")
        mark = "*" if field.key in overrides else " "
        later = "  ↻" if field.restart else ""
        say(f" {mark} {field.key:<24} {display(field, store.get(field.key))}{later}")
    say("\n* = modifié   ↻ = appliqué au prochain démarrage   "
        "(python bot.py settings help)")


def _report(say, field, value, changed):
    if not changed:
        say(f"{field.key} inchangé ({display(field, value)}).")
        return
    say(f"✅ {field.key} = {display(field, value)}")
    if field.restart:
        say("   ↻ pris en compte au prochain démarrage de Rosalie.")


def _group(text: str) -> str | None:
    text = text.strip().lower()
    for group in GROUPS:
        if group.lower() == text or group.lower().startswith(text):
            return group
    return None


# --- outils ------------------------------------------------------------------------------------
def _tools(store: ConfigStore, rest: list[str], say) -> int:
    disabled = list(store.get("disabled_tools"))
    if rest and rest[0] in ("enable", "disable") and len(rest) > 1:
        names = [name for part in rest[1:] for name in part.split(",") if name]
        if rest[0] == "disable":
            disabled += [name for name in names if name not in disabled]
        else:
            disabled = [name for name in disabled if name not in names]
        store.set("disabled_tools", disabled)
        say(f"✅ Outils désactivés : {', '.join(store.get('disabled_tools')) or '(aucun)'}")
        return 0
    if rest:
        say(USAGE)
        return 1
    current = None
    for tool in tool_catalog():
        group = tool["requires"] or "général"
        if group != current:
            current = group
            say(f"\n[{group}]")
        state = "  " if tool["name"] in disabled else "✓ "
        flags = (" ⚠️" if tool["confirm"] else "") + (" (invités)" if tool["guest"] else "")
        say(f" {state}{tool['name']:<24}{flags}")
    say("\n✓ = activé   ⚠️ = demande confirmation   "
        "(python bot.py settings tools disable <outil…>)")
    return 0


# --- personnalités ---------------------------------------------------------------------------
def _personas(store: ConfigStore, rest: list[str], say) -> int:
    action = rest[0].lower() if rest else "list"
    args = rest[1:]
    active = store.get("persona")
    if action == "list" and not args:
        for info in store.personas():
            kind = "intégrée, lecture seule" if info.builtin else "personnalisée"
            say(f" {'*' if info.name == active else ' '} {info.name:<24} {kind}, {info.size} octets")
        say("\n* = active   (python bot.py settings persona help)")
    elif action == "show" and len(args) == 1:
        text = store.persona_text(args[0])
        if text is None:
            raise SettingError(f"la personnalité « {args[0]} » n'existe pas")
        say(text.rstrip())
    elif action == "use" and len(args) == 1:
        store.set("persona", args[0])
        say(f"✅ Personnalité active : {store.get('persona')}")
    elif action == "add" and len(args) in (1, 2):
        text = Path(args[1]).read_text(encoding="utf-8") if len(args) == 2 else _edit("")
        store.save_persona(args[0], text, create=True)
        say(f"✅ Personnalité « {args[0].lower()} » créée (persona use {args[0].lower()} pour l'activer).")
    elif action == "copy" and len(args) == 2:
        text = store.persona_text(args[0])
        if text is None:
            raise SettingError(f"la personnalité « {args[0]} » n'existe pas")
        store.save_persona(args[1], text, create=True)
        say(f"✅ « {args[0].lower()} » copiée vers « {args[1].lower()} ».")
    elif action == "edit" and len(args) == 1:
        if store.is_builtin(args[0]):
            raise SettingError(f"« {args[0]} » est intégrée : persona copy {args[0]} <nom> d'abord")
        text = store.persona_text(args[0])
        if text is None:
            raise SettingError(f"la personnalité « {args[0]} » n'existe pas")
        edited = _edit(text)
        if edited.strip() == text.strip():
            say("Aucun changement.")
            return 0
        store.save_persona(args[0], edited, create=False)
        say(f"✅ « {args[0].lower()} » enregistrée.")
    elif action == "rename" and len(args) == 2:
        store.rename_persona(args[0], args[1])
        say(f"✅ « {args[0].lower()} » renommée en « {args[1].lower()} ».")
    elif action == "delete" and len(args) == 1:
        store.delete_persona(args[0])
        say(f"✅ « {args[0].lower()} » supprimée (active : {store.get('persona')}).")
    else:
        say(USAGE)
        return 1
    return 0


def _edit(text: str) -> str:
    """Ouvre $EDITOR (ou nano / notepad) sur un fichier temporaire et renvoie son contenu."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") \
        or ("notepad" if os.name == "nt" else "nano")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as file:
        file.write(text)
        path = file.name
    try:
        subprocess.run([*shlex.split(editor), path], check=True)
        return Path(path).read_text(encoding="utf-8")
    except (OSError, subprocess.CalledProcessError) as error:
        raise SettingError(f"éditeur « {editor} » : {error}") from None
    finally:
        Path(path).unlink(missing_ok=True)
