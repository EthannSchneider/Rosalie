import asyncio
import sys

from libs.config import load_config
from libs.config.schema import split_model
from libs.llm.ollama import OllamaClient
from libs.log import Log


def run():
    """python bot.py pull [model] — télécharge un modèle dans Ollama."""
    config, store = load_config()
    store.close()
    if len(sys.argv) > 2:
        model = sys.argv[2]
    else:
        provider, model = split_model(config.chat_model)
        if provider != "ollama":
            Log.info(f"Le modèle principal ({config.chat_model}) n'est pas un modèle Ollama : "
                     "rien à télécharger (python bot.py pull <modèle> pour en choisir un).")
            return
    asyncio.run(_pull(config.ollama_url, model))


async def _pull(url: str, model: str):
    client = OllamaClient(base_url=url, model=model)
    try:
        Log.info(f"Pulling {model} from {url} (peut prendre quelques minutes)...")
        await client.pull(model)
        Log.info(f"{model} is ready")
    finally:
        await client.close()
