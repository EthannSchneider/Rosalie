import asyncio
import sys

from libs.config import Config
from libs.llm.ollama import OllamaClient
from libs.log import Log


def run():
    """python bot.py pull [model] — télécharge un modèle dans Ollama."""
    config = Config.from_env()
    model = sys.argv[2] if len(sys.argv) > 2 else config.ollama_model
    asyncio.run(_pull(config.ollama_url, model))


async def _pull(url: str, model: str):
    client = OllamaClient(base_url=url, model=model)
    try:
        Log.info(f"Pulling {model} from {url} (peut prendre quelques minutes)...")
        await client.pull(model)
        Log.info(f"{model} is ready")
    finally:
        await client.close()
