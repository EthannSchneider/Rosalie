"""Session : état du site, installation (premier compte), connexion, déconnexion."""
from __future__ import annotations

from libs.config import legacy_owner_ids
from libs.config.schema import SettingError
from libs.log import Log
from libs.webui.controllers.base import Controller
from libs.webui.http import HttpError, Json, Request
from libs.models.accounts import SESSION_DAYS
from libs.models.user import User
from libs.webui.security import session_cookie
from libs.webui.views.user import session_json


class SessionController(Controller):
    def show(self, request: Request) -> Json:
        return Json(self.session_data(request.user))

    def setup(self, request: Request) -> Json:
        throttle = self.app.throttle
        throttle.check(request.client)
        try:
            user = self.app.accounts.setup(request.text("code"), request.text("username"),
                                           request.text("password"))
        except SettingError:
            throttle.failed(request.client)
            raise
        Log.command(f"Site web : superadmin « {user.username} » créé")
        return self.__logged_in(user)

    def login(self, request: Request) -> Json:
        throttle = self.app.throttle
        throttle.check(request.client)
        user = self.app.accounts.authenticate(request.text("username"), request.text("password"))
        if user is None:
            throttle.failed(request.client)
            raise HttpError(401, "nom d'utilisateur ou mot de passe incorrect")
        throttle.succeeded(request.client)
        return self.__logged_in(user)

    def logout(self, request: Request) -> Json:
        self.app.accounts.close_session(request.token)
        return Json({"ok": True}, headers={"Set-Cookie": session_cookie("", 0)})

    # --- partagé --------------------------------------------------------------------------
    def session_data(self, user: User | None) -> dict:
        app = self.app
        names = app.store.values()["names"]
        legacy = None
        if user is not None and user.has("users") and not app.accounts.discord_owner_ids():
            # transition : anciens OWNER_IDS encore utilisés tant que personne n'est lié
            legacy = [str(i) for i in sorted(legacy_owner_ids(app.store))]
        return session_json(name=(names[0] if names else "rosalie").capitalize(),
                            setup=app.accounts.count() == 0, user=user, chat=app.chat is not None,
                            legacy_owners=legacy)

    def __logged_in(self, user: User) -> Json:
        token = self.app.accounts.open_session(user.id)
        return Json(self.session_data(user),
                    headers={"Set-Cookie": session_cookie(token, SESSION_DAYS * 86400)})
