"""Sécurité du site : origine des requêtes, cookie de session, freinage des mots de passe.

- Les requêtes venant d'un autre site sont refusées (Origin, Sec-Fetch-Site, JSON obligatoire
  pour écrire) ; avec le cookie SameSite=Strict, ça ferme la porte aux attaques CSRF.
- En écoute locale, l'en-tête Host doit être local (contre le « DNS rebinding »).
"""
from __future__ import annotations

import ipaddress
import threading
import time
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

from libs.webui.http import HttpError

COOKIE = "rosalie_session"
LOCAL_NAMES = {"localhost", "127.0.0.1", "::1"}


def is_loopback(host: str) -> bool:
    host = host.strip("[]")
    if host in LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_origin(method: str, headers, local: bool):
    """Lève HttpError si la requête ne vient pas du site lui-même."""
    host = urlsplit(f"//{headers.get('Host', '')}").hostname or ""
    if local and not is_loopback(host):
        raise HttpError(403, "hôte non autorisé")
    if headers.get("Sec-Fetch-Site") == "cross-site":
        raise HttpError(403, "requête d'un autre site refusée")
    origin = headers.get("Origin")
    if origin and method != "GET" and (urlsplit(origin).hostname or "") != host:
        raise HttpError(403, "origine non autorisée")
    if method != "GET" and headers.get("Content-Type", "").split(";")[0] != "application/json":
        raise HttpError(415, "JSON attendu")


def session_token(headers) -> str | None:
    try:
        cookie = SimpleCookie(headers.get("Cookie", ""))
    except CookieError:
        return None
    morsel = cookie.get(COOKIE)
    return morsel.value if morsel else None


def session_cookie(token: str, max_age: int) -> str:
    return f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"


class Throttle:
    """Freine les essais de mot de passe : après 5 échecs, attente croissante (par adresse)."""

    def __init__(self):
        self.__lock = threading.Lock()
        self.__failures: dict[str, tuple[int, float]] = {}

    def check(self, client: str):
        with self.__lock:
            _, until = self.__failures.get(client, (0, 0.0))
        if time.time() < until:
            raise HttpError(429, f"trop d'essais, réessaie dans {int(until - time.time()) + 1} s")

    def failed(self, client: str):
        with self.__lock:
            count = self.__failures.get(client, (0, 0.0))[0] + 1
            delay = 0 if count < 5 else min(300, 2 ** (count - 4))
            self.__failures[client] = (count, time.time() + delay)

    def succeeded(self, client: str):
        with self.__lock:
            self.__failures.pop(client, None)
