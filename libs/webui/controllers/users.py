"""Utilisateurs (permission « users ») : liste, création, rôle, mot de passe, identifiant
Discord, suppression. Garde-fous : controllers/guards.py."""
from __future__ import annotations

from libs.log import Log
from libs.webui.controllers.base import Controller
from libs.webui.controllers.guards import can_assign, can_manage
from libs.webui.http import HttpError, Json, Request
from libs.webui.views.user import users_json


class UsersController(Controller):
    def index(self, request: Request) -> Json:
        return Json(users_json(self.app.accounts.users()))

    def create(self, request: Request) -> Json:
        accounts = self.app.accounts
        role = accounts.roles.require(str(request.optional("role", "user")))
        can_assign(request.user, role)
        discord = request.optional("discord_id")
        user = accounts.create(request.text("username"), request.text("password"), role.name,
                               discord if isinstance(discord, str) else None)
        Log.command(f"Site web ({request.user.username}) : compte « {user.username} » ({user.role}) créé")
        return Json(users_json(self.app.accounts.users()), status=201)

    def update(self, request: Request) -> Json:
        accounts = self.app.accounts
        target = self.__target(request)
        can_manage(request.user, target)
        if request.has("role"):
            role = accounts.roles.require(str(request.optional("role")))
            can_assign(request.user, role)
            accounts.set_role(target.id, role.name)
        if request.optional("password"):
            accounts.set_password(target.id, str(request.optional("password")))
        if request.has("discord_id"):
            value = request.optional("discord_id")
            accounts.set_discord(target.id, value if isinstance(value, str) else None)
        Log.command(f"Site web ({request.user.username}) : compte « {target.username} » modifié")
        return Json(users_json(accounts.users()))

    def destroy(self, request: Request) -> Json:
        target = self.__target(request)
        can_manage(request.user, target)
        if target.id == request.user.id:
            raise HttpError(400, "tu ne peux pas supprimer ton propre compte")
        self.app.accounts.delete(target.id)
        Log.command(f"Site web ({request.user.username}) : compte « {target.username} » supprimé")
        return Json(users_json(self.app.accounts.users()))

    def __target(self, request: Request):
        user = self.app.accounts.get(request.int_param("id"))
        if user is None:
            raise HttpError(404, "ce compte n'existe pas")
        return user
