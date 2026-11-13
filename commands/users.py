"""python bot.py users … — gérer les comptes (storages/rosalie.sqlite3).

Utile pour créer le superadmin sans passer par le code d'installation, ou pour se dépanner
(mot de passe oublié, dernier superadmin…).
"""
from __future__ import annotations

import getpass
import sys
import time

from libs.config import storage_dir
from libs.config.schema import SettingError
from libs.models import Accounts, main_database
from libs.models.user import ROLES

USAGE = f"""Comptes du site web de Rosalie

  python bot.py users                           liste
  python bot.py users add <nom> [--role ROLE] [--discord ID]   créer (mot de passe demandé)
  python bot.py users discord <nom> <ID|->      lier son identifiant Discord (- = délier)
  python bot.py users passwd <nom>              changer le mot de passe (ferme ses sessions)
  python bot.py users role <nom> <ROLE>         changer le rôle
  python bot.py users delete <nom>

Rôles : {", ".join(ROLES)}
  superadmin  tout : réglages de Rosalie, personnalités, comptes
  admin       la fait agir (outils, souvenirs, code), sur le chat web et sur Discord
  user        discute seulement, comme un invité (discussion et recherche)

Sur Discord, Rosalie obéit aux comptes admin et superadmin liés à leur identifiant Discord
(clic droit sur ton profil > Copier l'identifiant, mode développeur requis)."""


def run():
    accounts = Accounts(main_database(storage_dir()))
    try:
        sys.exit(main(sys.argv[2:], accounts))
    except SettingError as error:
        print(f"❌ {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        accounts.close()


def main(args: list[str], accounts: Accounts, out=None, ask_password=None) -> int:
    out = out or sys.stdout
    ask_password = ask_password or _ask_password

    def say(text: str = ""):
        print(text, file=out)

    command = args[0].lower() if args else "list"
    rest = args[1:]
    if command == "list" and not rest:
        users = accounts.users()
        if not users:
            say("Aucun compte. Crée le superadmin : python bot.py users add <nom> --role superadmin")
        for user in users:
            seen = time.strftime("%d.%m.%Y %H:%M", time.localtime(user.last_login)) \
                if user.last_login else "jamais connecté"
            discord = f"discord {user.discord_id}" if user.discord_id else "pas de Discord"
            say(f"  {user.username:<20} {user.role:<11} {discord:<28} {seen}")
    elif command == "add" and rest:
        options = {}
        for flag in ("--role", "--discord"):
            if flag in rest:
                index = rest.index(flag)
                if index + 1 >= len(rest):
                    say(USAGE)
                    return 1
                options[flag] = rest[index + 1]
                rest = rest[:index] + rest[index + 2:]
        if len(rest) != 1:
            say(USAGE)
            return 1
        user = accounts.create(rest[0], ask_password(), options.get("--role", "user"),
                               options.get("--discord"))
        say(f"✅ Compte « {user.username} » ({user.role}) créé.")
    elif command == "discord" and len(rest) == 2:
        user = _find(accounts, rest[0])
        accounts.set_discord(user.id, None if rest[1] == "-" else rest[1])
        say(f"✅ « {user.username} » : " + ("identifiant Discord retiré." if rest[1] == "-"
                                           else f"lié à l'identifiant Discord {rest[1]}."))
    elif command == "passwd" and len(rest) == 1:
        user = _find(accounts, rest[0])
        accounts.set_password(user.id, ask_password())
        say(f"✅ Mot de passe de « {user.username} » changé (ses sessions sont fermées).")
    elif command == "role" and len(rest) == 2:
        user = _find(accounts, rest[0])
        accounts.set_role(user.id, rest[1])
        say(f"✅ « {user.username} » est maintenant {rest[1]}.")
    elif command == "delete" and len(rest) == 1:
        user = _find(accounts, rest[0])
        accounts.delete(user.id)
        say(f"✅ « {user.username} » supprimé.")
    else:
        say(USAGE)
        return 0 if command in ("help", "-h", "--help") else 1
    return 0


def _find(accounts: Accounts, username: str):
    user = accounts.find(username)
    if user is None:
        raise SettingError(f"« {username} » n'existe pas")
    return user


def _ask_password() -> str:
    first = getpass.getpass("Mot de passe : ")
    if getpass.getpass("Encore une fois : ") != first:
        raise SettingError("les deux mots de passe sont différents")
    return first
