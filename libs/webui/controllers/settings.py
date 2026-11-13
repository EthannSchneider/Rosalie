"""Réglages de Rosalie (superadmin) : schéma et valeurs, modèles Ollama, personnalités."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from libs.config.schema import tool_catalog
from libs.log import Log
from libs.webui.controllers.base import Controller
from libs.webui.http import HttpError, Json, Request
from libs.webui.views.settings import persona_json, state_json


class SettingsController(Controller):
    def show(self, request: Request) -> Json:
        return Json(self.__state())

    def update(self, request: Request) -> Json:
        changes = request.optional("changes")
        if not isinstance(changes, dict):
            raise HttpError(400, "« changes » attendu")
        changed = self.app.store.update(changes)
        Log.command(f"Site web ({request.user.username}) : réglages modifiés ({', '.join(changed) or 'aucun'})")
        return Json({"changed": changed, "state": self.__state()})

    def models(self, request: Request) -> Json:
        """Modèles installés dans Ollama, pour les suggestions (vide si injoignable)."""
        url = self.app.store.values()["ollama_url"].rstrip("/") + "/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return Json({"models": []})
        return Json({"models": sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))})

    # --- personnalités --------------------------------------------------------------------
    def persona(self, request: Request) -> Json:
        name = request.params["name"]
        text = self.app.store.persona_text(name)
        if text is None:
            raise HttpError(404, f"la personnalité « {name} » n'existe pas")
        return Json(persona_json(name, text, self.app.store.is_builtin(name)))

    def save_persona(self, request: Request) -> Json:
        name = request.params["name"]
        create = request.optional("create")
        self.app.store.save_persona(name, request.text("text"),
                                    create=create if isinstance(create, bool) else None)
        Log.command(f"Site web ({request.user.username}) : personnalité « {name} » enregistrée")
        return Json({"state": self.__state()})

    def rename_persona(self, request: Request) -> Json:
        self.app.store.rename_persona(request.params["name"], request.text("to"))
        return Json({"state": self.__state()})

    def delete_persona(self, request: Request) -> Json:
        name = request.params["name"]
        self.app.store.delete_persona(name)
        Log.command(f"Site web ({request.user.username}) : personnalité « {name} » supprimée")
        return Json({"state": self.__state()})

    def __state(self) -> dict:
        self.app.store.refresh()
        return state_json(self.app.store, tool_catalog())
