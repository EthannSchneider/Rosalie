"""Le peu de l'API GitHub qu'il faut : ouvrir, lire et fusionner une pull request.

Appels bloquants (urllib) : à lancer avec `asyncio.to_thread`. Le jeton ne sort que dans
l'en-tête Authorization ; les erreurs ne contiennent que le message de GitHub.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

API = "https://api.github.com"


class GitHubError(Exception):
    """Refus ou panne de GitHub : le message est montré tel quel."""


class GitHub:
    def __init__(self, token: str, api: str = API, timeout: int = 30):
        self.__token = token
        self.__api = api.rstrip("/")
        self.__timeout = timeout

    def create_pull(self, repo: str, *, title: str, head: str, base: str, body: str,
                    draft: bool = False) -> dict:
        payload = {"title": title, "head": head, "base": base, "body": body, "draft": draft}
        try:
            return self.__call("POST", f"/repos/{repo}/pulls", payload)
        except GitHubError:
            if not draft:
                raise
            # les brouillons ne sont pas disponibles sur tous les dépôts : PR normale (le texte
            # de la PR signale de toute façon les vérifications en échec)
            return self.__call("POST", f"/repos/{repo}/pulls", {**payload, "draft": False})

    def pull(self, repo: str, number: int) -> dict:
        return self.__call("GET", f"/repos/{repo}/pulls/{number}")

    def merge_pull(self, repo: str, number: int, *, sha: str, method: str = "squash") -> dict:
        """sha : le commit que Rosalie a poussé. Si la branche a bougé depuis, GitHub refuse."""
        return self.__call("PUT", f"/repos/{repo}/pulls/{number}/merge",
                           {"sha": sha, "merge_method": method})

    def __call(self, method: str, path: str, payload: dict | None = None) -> dict:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "rosalie-evolve"}
        if self.__token:
            headers["Authorization"] = f"Bearer {self.__token}"
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.__api + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.__timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8"))
                message = detail.get("message", "")
                extra = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e)
                                  for e in detail.get("errors", []))
                message = f"{message} ({extra})" if extra else message
            except (ValueError, AttributeError):
                message = ""
            raise GitHubError(f"GitHub a refusé (HTTP {error.code}) : {message or error.reason}") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise GitHubError(f"GitHub injoignable : {error}") from None
