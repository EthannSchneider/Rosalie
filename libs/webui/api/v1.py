"""API v1 : /api/v1/…  — la table complète des routes, leurs droits et leurs contrôleurs.

Accès : public (sans compte) · user (tout compte connecté) · une permission (libs/models/role.py)
ou un tuple (au moins une des permissions).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from libs.webui.controllers import (AccountController, ChatController, RolesController,
                                    SessionController, SettingsController, UsersController)
from libs.webui.router import Router

if TYPE_CHECKING:
    from libs.webui.server import WebServer

PREFIX = "/api/v1"


def build(app: WebServer) -> tuple[Router, SimpleNamespace]:
    c = SimpleNamespace(session=SessionController(app), account=AccountController(app),
                        settings=SettingsController(app), users=UsersController(app),
                        roles=RolesController(app), chat=ChatController(app))
    r = Router(PREFIX)

    # Session
    r.add("GET", "/session", c.session.show, access="public")
    r.add("POST", "/session/setup", c.session.setup, access="public")
    r.add("POST", "/session/login", c.session.login, access="public")
    r.add("POST", "/session/logout", c.session.logout, access="public")

    # Mon compte
    r.add("PUT", "/account/password", c.account.change_password)
    r.add("PUT", "/account/discord", c.account.link_discord)

    # Réglages de Rosalie (le schéma sert aussi à la page Personnalités)
    r.add("GET", "/settings", c.settings.show, access=("settings", "personas"))
    r.add("PATCH", "/settings", c.settings.update, access="settings")
    r.add("GET", "/settings/models", c.settings.models, access="settings")

    # Personnalités
    r.add("GET", "/personas/{name}", c.settings.persona, access="personas")
    r.add("PUT", "/personas/{name}", c.settings.save_persona, access="personas")
    r.add("POST", "/personas/{name}/activate", c.settings.activate_persona, access="personas")
    r.add("POST", "/personas/{name}/rename", c.settings.rename_persona, access="personas")
    r.add("DELETE", "/personas/{name}", c.settings.delete_persona, access="personas")

    # Rôles (la liste sert aussi à la page Utilisateurs)
    r.add("GET", "/roles", c.roles.index, access=("roles", "users"))
    r.add("POST", "/roles", c.roles.create, access="roles")
    r.add("PATCH", "/roles/{name}", c.roles.update, access="roles")
    r.add("DELETE", "/roles/{name}", c.roles.destroy, access="roles")

    # Utilisateurs
    r.add("GET", "/users", c.users.index, access="users")
    r.add("POST", "/users", c.users.create, access="users")
    r.add("PATCH", "/users/{id}", c.users.update, access="users")
    r.add("DELETE", "/users/{id}", c.users.destroy, access="users")

    # Chat (permission « chat », quand Rosalie tourne)
    r.add("GET", "/chat/messages", c.chat.history, access="chat")
    r.add("POST", "/chat/messages", c.chat.send, access="chat")
    r.add("GET", "/chat/events", c.chat.events, access="chat")
    r.add("POST", "/chat/typing", c.chat.typing, access="chat")
    r.add("DELETE", "/chat/messages", c.chat.reset, access="chat")
    r.add("POST", "/chat/confirmations/{id}", c.chat.confirm, access="chat")
    r.add("GET", "/chat/files/{id}", c.chat.file, access="chat")
    return r, c
