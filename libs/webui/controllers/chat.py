"""Chat : la conversation privée du compte avec Rosalie (seulement quand elle tourne).

Le travail (enregistrer, transmettre à Rosalie, confirmations) est fait par l'interface web
(interfaces/web/) ; ce contrôleur ne fait que traduire HTTP <-> interface.
"""
from __future__ import annotations

import json
import queue

from libs.webui.controllers.base import Controller
from libs.webui.http import File, HttpError, Json, Request, Stream
from libs.webui.views.chat import history_json, message_json

PING_EVERY = 20   # secondes : garde le flux ouvert et détecte les onglets fermés
INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class ChatController(Controller):
    @property
    def chat(self):
        if self.app.chat is None:
            raise HttpError(503, "le chat n'est disponible que quand Rosalie tourne (python bot.py)")
        return self.app.chat

    def history(self, request: Request) -> Json:
        before = request.query.get("before")
        try:
            before = int(before) if before else None
        except ValueError:
            raise HttpError(400, "« before » doit être un nombre") from None
        return Json(history_json(self.chat.history(request.user, before)))

    def send(self, request: Request) -> Json:
        return Json({"message": message_json(self.chat.post(request.user, request.text("text")))}, status=201)

    def typing(self, request: Request) -> Json:
        self.chat.user_typing(request.user)
        return Json({"ok": True})

    def reset(self, request: Request) -> Json:
        self.chat.reset(request.user)
        return Json({"ok": True})

    def confirm(self, request: Request) -> Json:
        accept = request.optional("accept")
        if not isinstance(accept, bool):
            raise HttpError(400, "« accept » attendu")
        self.chat.answer(request.user, request.int_param("id"), accept)
        return Json({"ok": True})

    def file(self, request: Request) -> File:
        found = self.chat.file(request.user, request.params["id"])
        if found is None:
            raise HttpError(404, "fichier introuvable")
        from pathlib import Path
        return File(Path(found.path), found.name, found.type, inline=found.type in INLINE_TYPES)

    def events(self, request: Request) -> Stream:
        """Flux temps réel (Server-Sent Events) jusqu'à la fermeture de l'onglet."""
        hub = self.chat.hub
        user_id = request.user.id
        listener = hub.subscribe(user_id)
        closing = self.app.closing

        def produce():
            yield "retry: 3000\n\n"
            while not closing.is_set():
                try:
                    event = listener.get(timeout=PING_EVERY)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return Stream(produce(), close=lambda: hub.unsubscribe(user_id, listener))
