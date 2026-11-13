"""Routeur : associe (méthode, chemin) à un contrôleur, avec le niveau d'accès requis.

    router.add("PATCH", "/users/{id}", users.update, access="users")

Niveaux d'accès :
  public          sans compte (session, connexion, installation)
  user            tout compte connecté
  <permission>    le rôle du compte doit avoir cette permission (libs/models/role.py) ;
  (a, b)          … ou au moins une de celles-ci
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from libs.models.role import PERMISSIONS
from libs.webui.http import HttpError, Request

ACCESS = ("public", "user", *PERMISSIONS)


@dataclass(frozen=True)
class Route:
    method: str
    parts: tuple[str, ...]
    handler: Callable[[Request], object]
    access: str | tuple[str, ...]

    def match(self, parts: list[str]) -> dict[str, str] | None:
        if len(parts) != len(self.parts):
            return None
        params = {}
        for expected, actual in zip(self.parts, parts):
            if expected.startswith("{") and expected.endswith("}"):
                params[expected[1:-1]] = actual
            elif expected != actual:
                return None
        return params


class Router:
    def __init__(self, prefix: str):
        self.prefix = prefix.rstrip("/")
        self.routes: list[Route] = []

    def add(self, method: str, path: str, handler: Callable[[Request], object],
            access: str | tuple[str, ...] = "user"):
        for level in (access if isinstance(access, tuple) else (access,)):
            if level not in ACCESS:
                raise ValueError(f"accès inconnu : {level}")
        self.routes.append(Route(method, _split(path), handler, access))

    def owns(self, path: str) -> bool:
        return path == self.prefix or path.startswith(self.prefix + "/")

    def resolve(self, method: str, path: str) -> tuple[Route, dict[str, str]]:
        parts = _split(path[len(self.prefix):])
        allowed = False
        for route in self.routes:
            params = route.match(parts)
            if params is None:
                continue
            if route.method == method:
                return route, params
            allowed = True
        raise HttpError(405 if allowed else 404, "méthode non permise" if allowed else "route inconnue")


def authorize(route: Route, request: Request):
    """Vérifie que le compte connecté a le droit d'appeler cette route."""
    user = request.user
    if route.access == "public":
        return
    if user is None:
        raise HttpError(401, "connexion requise")
    if route.access == "user":
        return
    needed = route.access if isinstance(route.access, tuple) else (route.access,)
    if not any(user.has(permission) for permission in needed):
        names = " ou ".join(PERMISSIONS[p][0] for p in needed)
        raise HttpError(403, f"permission requise : {names}")


def _split(path: str) -> tuple[str, ...]:
    from urllib.parse import unquote
    return tuple(unquote(part) for part in path.strip("/").split("/") if part)
