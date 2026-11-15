"""Évolution du code (permission « evolve », réservée au superadmin) : demander une modification,
suivre les opérations, fusionner la pull request, mettre à jour et redémarrer.

Le travail est fait par libs/evolve (dans la boucle asyncio de Rosalie) ; ce contrôleur traduit
HTTP <-> Evolver. Les droits sont vérifiés par la route (api/v1.py) : jamais par le navigateur.
"""
from __future__ import annotations

import asyncio
import time

from libs.evolve import Brief
from libs.evolve.github import GitHubError
from libs.log import Log
from libs.webui.controllers.base import Controller
from libs.webui.http import HttpError, Json, Request
from libs.webui.views.evolution import evolution_json

REFRESH_EVERY = 30   # secondes entre deux lectures de l'état des pull requests sur GitHub
CALL_TIMEOUT = 60


class EvolutionController(Controller):
    def __init__(self, app):
        super().__init__(app)
        self.__refreshed = 0.0

    @property
    def evolver(self):
        if self.app.chat is None:
            raise HttpError(503, "l'évolution du code n'est disponible que quand Rosalie tourne (python bot.py)")
        return self.app.chat.rosalie.evolver

    def index(self, request: Request) -> Json:
        return Json(self.__state(refresh=True))

    def create(self, request: Request) -> Json:
        brief = Brief(title=request.text("title"), reason=request.text("reason"),
                      objective=request.text("objective"),
                      context=str(request.optional("context", "") or ""),
                      constraints=str(request.optional("constraints", "") or ""),
                      criteria=str(request.optional("criteria", "") or ""))
        user = request.user
        evolver = self.evolver

        async def start():   # start() crée une tâche : il doit tourner dans la boucle de Rosalie
            return evolver.start(brief, author=user.username, conversation=self.app.chat.key_of(user))
        self.__call(start())
        return Json(self.__state(), status=201)

    def merge(self, request: Request) -> Json:
        operation_id = request.int_param("id")
        self.__call(self.evolver.merge(operation_id, request.user.username))
        Log.command(f"Site web ({request.user.username}) : évolution #{operation_id}, pull request fusionnée")
        return Json(self.__state())

    def update(self, request: Request) -> Json:
        operation_id = request.int_param("id")
        self.__call(self.evolver.request_update(operation_id, request.user.username))
        Log.command(f"Site web ({request.user.username}) : évolution #{operation_id}, mise à jour demandée")
        return Json(self.__state())

    def __call(self, coroutine):
        """Exécute dans la boucle asyncio de Rosalie (le serveur HTTP tourne dans des fils)."""
        loop = self.app.chat.loop
        if loop is None or loop.is_closed():
            coroutine.close()
            raise HttpError(503, "Rosalie n'est pas prête")
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(CALL_TIMEOUT)
        except GitHubError as error:
            raise HttpError(502, self.evolver.redact(str(error))) from None
        except TimeoutError:
            future.cancel()
            raise HttpError(504, "GitHub met trop de temps à répondre") from None

    def __state(self, refresh: bool = False) -> dict:
        evolver = self.evolver
        notice = ""
        evolver.sync()
        if refresh and time.monotonic() - self.__refreshed >= REFRESH_EVERY:
            self.__refreshed = time.monotonic()
            for operation in evolver.operations.with_status("pr_open"):   # fusionnée sur GitHub ?
                try:
                    self.__call(evolver.refresh(operation.id))
                except HttpError as error:
                    notice = str(error)
                    break
        return evolution_json(evolver, evolver.operations.recent(), notice)
