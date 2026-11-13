"""Rôles (permission « roles ») : liste, création, permissions, suppression.

La liste (GET) sert aussi à la page Utilisateurs (choisir un rôle) : accès « users » ou « roles ».
"""
from __future__ import annotations

from libs.log import Log
from libs.webui.controllers.base import Controller
from libs.webui.controllers.guards import can_grant
from libs.webui.http import HttpError, Json, Request
from libs.webui.views.user import roles_json


class RolesController(Controller):
    def index(self, request: Request) -> Json:
        return Json(self.__list())

    def create(self, request: Request) -> Json:
        permissions = self.__permissions(request)
        can_grant(request.user, permissions)
        role = self.app.accounts.roles.create(request.text("name"), request.text("label"), permissions,
                                              str(request.optional("description", "")))
        Log.command(f"Site web ({request.user.username}) : rôle « {role.name} » créé ({', '.join(role.permissions)})")
        return Json(self.__list(), status=201)

    def update(self, request: Request) -> Json:
        roles = self.app.accounts.roles
        name = request.params["name"]
        current = roles.require(name)
        permissions = self.__permissions(request) if request.has("permissions") else None
        if permissions is not None:
            # on ne touche (ajoute ou retire) que des permissions qu'on a soi-même
            can_grant(request.user, set(permissions) ^ set(current.permissions))
        label = request.optional("label")
        description = request.optional("description")
        roles.update(name, label=label if isinstance(label, str) else None,
                     description=description if isinstance(description, str) else None,
                     permissions=permissions)
        Log.command(f"Site web ({request.user.username}) : rôle « {name} » modifié")
        return Json(self.__list())

    def destroy(self, request: Request) -> Json:
        name = request.params["name"]
        role = self.app.accounts.roles.require(name)
        can_grant(request.user, role.granted)
        self.app.accounts.roles.delete(name)
        Log.command(f"Site web ({request.user.username}) : rôle « {name} » supprimé")
        return Json(self.__list())

    def __list(self) -> dict:
        roles = self.app.accounts.roles
        return roles_json(roles.all(), roles.counts())

    @staticmethod
    def __permissions(request: Request) -> list[str]:
        value = request.optional("permissions", [])
        if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
            raise HttpError(400, "« permissions » : liste attendue")
        return value
