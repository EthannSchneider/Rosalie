from libs.config import WebUIOptions, load_config
from libs.log import Log
from libs.webui import WebServer


def run():
    """python bot.py web — seulement le site (réglages, comptes), sans lancer Rosalie.
    Le chat n'y est pas disponible. Si Rosalie tourne à côté, elle suit les réglages à chaud."""
    config, store = load_config()
    options = WebUIOptions.from_env()
    try:
        server = WebServer(store, options.host, options.port, storage=config.storage_dir)
    except OSError as error:
        Log.error(f"Site web : {error}")
        store.close()
        return
    Log.info(f"Site web (réglages seulement) : {server.url} (Ctrl+C pour arrêter)")
    server.announce_setup()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        store.close()
