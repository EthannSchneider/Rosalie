"""python bot.py roles … — gérer les rôles et leurs permissions (storages/rosalie.sqlite3).

La ligne de commande a tous les droits (c'est ta machine) : pas de garde-fou d'élévation ici.
"""
from __future__ import annotations

import sys

from libs.config import storage_dir
from libs.config.schema import SettingError
from libs.models import PERMISSIONS, Accounts, main_database

USAGE = """Rôles de Rosalie et leurs permissions

  python bot.py roles                                     liste
  python bot.py roles permissions                         les permissions possibles
  python bot.py roles add <nom> <libellé> [perm,perm…]    créer
  python bot.py roles set <nom> <perm,perm…|->            changer ses permissions (- = aucune)
  python bot.py roles label <nom> <libellé>               renommer (le libellé affiché)
  python bot.py roles delete <nom>                        supprimer (s'il n'est plus attribué)

« superadmin » est verrouillé : il a toujours toutes les permissions."""


def run():
    accounts = Accounts(main_database(storage_dir()))
    try:
        sys.exit(main(sys.argv[2:], accounts))
    except SettingError as error:
        print(f"❌ {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        accounts.close()


def main(args: list[str], accounts: Accounts, out=None) -> int:
    out = out or sys.stdout

    def say(text: str = ""):
        print(text, file=out)

    roles = accounts.roles
    command = args[0].lower() if args else "list"
    rest = args[1:]
    if command == "list" and not rest:
        counts = roles.counts()
        for role in roles.all():
            lock = " 🔒" if role.locked else ""
            say(f"  {role.name:<14} {role.label:<16} {counts.get(role.name, 0):>3} compte(s)  "
                f"{', '.join(sorted(role.granted, key=list(PERMISSIONS).index)) or '(aucune)'}{lock}")
    elif command == "permissions" and not rest:
        for name, (label, description) in PERMISSIONS.items():
            say(f"  {name:<10} {label} — {description}")
    elif command == "add" and len(rest) in (2, 3):
        role = roles.create(rest[0], rest[1], _perms(rest[2]) if len(rest) == 3 else [])
        say(f"✅ Rôle « {role.name} » créé : {', '.join(role.permissions) or '(aucune permission)'}")
    elif command == "set" and len(rest) == 2:
        role = roles.update(rest[0], permissions=_perms(rest[1]))
        say(f"✅ « {role.name} » : {', '.join(role.permissions) or '(aucune permission)'}")
    elif command == "label" and len(rest) >= 2:
        role = roles.update(rest[0], label=" ".join(rest[1:]))
        say(f"✅ « {role.name} » s'affiche maintenant « {role.label} »")
    elif command == "delete" and len(rest) == 1:
        roles.delete(rest[0])
        say(f"✅ Rôle « {rest[0]} » supprimé.")
    else:
        say(USAGE)
        return 0 if command in ("help", "-h", "--help") else 1
    return 0


def _perms(text: str) -> list[str]:
    return [] if text.strip() == "-" else [p.strip() for p in text.split(",") if p.strip()]
