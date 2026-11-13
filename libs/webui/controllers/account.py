"""Mon compte : ce que chacun règle pour lui-même (mot de passe, identifiant Discord)."""
from __future__ import annotations

from libs.log import Log
from libs.webui.controllers.base import Controller
from libs.webui.http import HttpError, Json, Request


class AccountController(Controller):
    def change_password(self, request: Request) -> Json:
        accounts = self.app.accounts
        if not accounts.verify_password(request.user.id, request.text("current")):
            raise HttpError(400, "mot de passe actuel incorrect")
        accounts.set_password(request.user.id, request.text("password"), keep_session=request.token)
        return Json({"ok": True})

    def link_discord(self, request: Request) -> Json:
        value = request.optional("discord_id")
        self.app.accounts.set_discord(request.user.id, value if isinstance(value, str) else None)
        Log.command(f"Site web : « {request.user.username} » a "
                    f"{'lié' if value else 'délié'} son identifiant Discord")
        return Json(self.app.controllers.session.session_data(self.app.accounts.get(request.user.id)))
