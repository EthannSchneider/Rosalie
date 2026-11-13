"""Vues JSON : réglages (schéma + valeurs), personnalités, outils. Les secrets ne sont jamais
renvoyés : seulement s'ils sont définis."""
from __future__ import annotations

from libs.config.schema import FIELDS, GROUPS
from libs.config.store import DEFAULT_PERSONA, ConfigStore


def state_json(store: ConfigStore, tools: list[dict]) -> dict:
    overrides = store.overrides()
    values = store.values()
    fields = []
    for field in FIELDS:
        info = field.public()
        info["modified"] = field.key in overrides
        if field.kind == "secret":
            info["is_set"] = bool(values[field.key])
            info["default"] = ""
        else:
            info["value"] = values[field.key]
        fields.append(info)
    return {
        "groups": list(GROUPS),
        "fields": fields,
        "personas": [persona_info_json(p, values["persona"]) for p in store.personas()],
        "tools": tools,
        "path": str(store.path),
    }


def persona_info_json(info, active: str) -> dict:
    return {"name": info.name, "builtin": info.builtin, "size": info.size,
            "active": info.name == active, "default": info.name == DEFAULT_PERSONA}


def persona_json(name: str, text: str, builtin: bool) -> dict:
    return {"name": name.lower(), "text": text, "builtin": builtin}
