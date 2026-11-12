import importlib
import sys

from dotenv import load_dotenv

from libs.log import Log


COMMANDS = {
    "rosalie": "rosalie",        # lance Rosalie avec les interfaces du .env (INTERFACES)
    "chat": "chat",              # parle avec elle dans le terminal (sans Discord)
    "pull": "pull",            # télécharge le modèle Ollama configuré
    "test": "test",            # lance les tests unitaires
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
