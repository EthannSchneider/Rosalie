import asyncio

from interfaces import load
from libs.config import Config
from libs.core.rosalie import Rosalie
from libs.log import Log


def run(interfaces: tuple[str, ...] | None = None):
    """Lance Rosalie avec les interfaces du .env (INTERFACES), ou celles demandées."""
    asyncio.run(_run(interfaces))


async def _run(interfaces: tuple[str, ...] | None):
    config = Config.from_env()
    rosalie = Rosalie(config)
    for name in interfaces or config.interfaces:
        try:
            rosalie.add_interface(load(name, rosalie))
        except Exception as error:
            Log.error(f"Interface {name} : {error}")
    await rosalie.run()
