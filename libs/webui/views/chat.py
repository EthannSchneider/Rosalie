"""Vues JSON : messages du chat et événements temps réel."""
from __future__ import annotations

from libs.models.chat import ChatMessage


def message_json(message: ChatMessage) -> dict:
    return {"id": message.id, "author": message.author, "text": message.text, "kind": message.kind,
            "meta": message.meta, "created": message.created}


def history_json(messages: list[ChatMessage]) -> dict:
    return {"messages": [message_json(m) for m in messages]}


def message_event(message: ChatMessage) -> dict:
    return {"type": "message", "message": message_json(message)}


def update_event(message: ChatMessage) -> dict:
    return {"type": "update", "message": message_json(message)}


def typing_event(on: bool) -> dict:
    return {"type": "typing", "on": on}
