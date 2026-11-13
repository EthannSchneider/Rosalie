import importlib
import sys

from dotenv import load_dotenv

from libs.log import Log


COMMANDS = {
    "rosalie": "rosalie",        # lance Rosalie : Discord + site web (tout sauf le terminal)
    "chat": "chat",              # parle avec elle dans le terminal (sans Discord)
    "pull": "pull",            # télécharge le modèle Ollama configuré
    "test": "test",            # lance les tests unitaires
    "settings": "settings",    # voir / modifier les réglages (storages/config.sqlite3)
    "web": "web",              # seulement le site web (réglages, comptes ; sans chat)
    "users": "users",          # comptes du site web
}


def main():
    load_dotenv()

    command_name = sys.argv[1] if len(sys.argv) > 1 else "rosalie"
    module_name = COMMANDS.get(command_name)
    if module_name is None:
        Log.error(f"Subcommand '{command_name}' not found. "
                  f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)

    command = importlib.import_module(f"commands.{module_name}")
    command.run()
