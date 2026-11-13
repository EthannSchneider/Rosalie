from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.webui.server import WebServer


class Controller:
    """Accès aux services du site : app.store (réglages), app.accounts (comptes),
    app.chat (interface web de Rosalie, None sans elle), app.throttle."""

    def __init__(self, app: WebServer):
        self.app = app
