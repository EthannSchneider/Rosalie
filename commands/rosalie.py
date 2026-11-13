import asyncio

from interfaces import DEFAULT, load
from libs.config import load_config
from libs.core.rosalie import Rosalie
from libs.log import Log


def run(interfaces: tuple[str, ...] = DEFAULT):
    """Lance Rosalie : toutes les interfaces sauf le terminal (Discord, site web),
    ou celles demandées (python bot.py chat -> terminal)."""
    asyncio.run(_run(interfaces))


async def _run(interfaces: tuple[str, ...]):
    config, store = load_config()
    rosalie = Rosalie(config, store)
    for name in interfaces:
        try:
            rosalie.add_interface(load(name, rosalie))
        except Exception as error:
            Log.error(f"Interface {name} : {error}")
    await rosalie.run()
