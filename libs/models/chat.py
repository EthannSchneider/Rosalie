"""Modèle : l'historique du chat web et les fichiers envoyés par Rosalie (storages/rosalie.sqlite3).

L'historique complet est gardé pour l'affichage ; ce que Rosalie « se rappelle » reste sa
mémoire courte habituelle (libs/conversation/memory.py, HISTORY_SIZE messages).
"""
from __future__ import annotations

import mimetypes
import re
import secrets
import time
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Float, Index, Integer, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from libs.db import Database
from libs.models.bases import MainBase

PAGE = 50


class ChatMessage(MainBase):
    __tablename__ = "messages"
    __table_args__ = (Index("messages_conversation", "conversation", "id"),
                      {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation: Mapped[str] = mapped_column(Text, nullable=False)   # clé « web:<id du compte> »
    author: Mapped[str] = mapped_column(Text, nullable=False)         # user | rosalie
    text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="text")   # text | confirm
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created: Mapped[float] = mapped_column(Float, nullable=False)


class ChatFile(MainBase):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)


class ChatLog:
    def __init__(self, path: Path, files_dir: Path):
        self.db = Database(path, "main")
        self.files_dir = files_dir
        self.__expire_pending()

    def close(self):
        self.db.close()

    def __expire_pending(self):
        """Une confirmation en attente ne survit pas à un redémarrage."""
        with self.db.transaction() as session:
            for message in session.scalars(select(ChatMessage).where(ChatMessage.kind == "confirm")):
                if message.meta.get("status") == "pending":
                    message.meta = {**message.meta, "status": "expired"}

    def add(self, conversation: str, author: str, text: str, kind: str = "text",
            meta: dict | None = None) -> ChatMessage:
        message = ChatMessage(conversation=conversation, author=author, text=text, kind=kind,
                              meta=meta or {}, created=time.time())
        with self.db.transaction() as session:
            session.add(message)
        return message

    def get(self, message_id: int) -> ChatMessage | None:
        with self.db.read() as session:
            return session.get(ChatMessage, message_id)

    def update_meta(self, message_id: int, **changes) -> ChatMessage | None:
        with self.db.transaction() as session:
            message = session.get(ChatMessage, message_id)
            if message is None:
                return None
            message.meta = {**message.meta, **changes}   # nouvel objet : l'ORM voit le changement
        return message

    def history(self, conversation: str, before: int | None = None, limit: int = PAGE) -> list[ChatMessage]:
        query = select(ChatMessage).where(ChatMessage.conversation == conversation)
        if before:
            query = query.where(ChatMessage.id < before)
        with self.db.read() as session:
            messages = list(session.scalars(query.order_by(ChatMessage.id.desc()).limit(limit)))
        return messages[::-1]

    def clear(self, conversation: str):
        with self.db.transaction() as session:
            paths = list(session.scalars(select(ChatFile.path).where(ChatFile.conversation == conversation)))
            session.execute(delete(ChatMessage).where(ChatMessage.conversation == conversation))
            session.execute(delete(ChatFile).where(ChatFile.conversation == conversation))
        for path in paths:
            Path(path).unlink(missing_ok=True)

    # --- fichiers envoyés par Rosalie -------------------------------------------------------
    def save_file(self, conversation: str, name: str, data: bytes) -> dict:
        self.files_dir.mkdir(parents=True, exist_ok=True)
        file_id = secrets.token_urlsafe(12)
        safe = re.sub(r"[^\w.-]+", "_", name)[-80:] or "fichier"
        path = self.files_dir / f"{file_id}-{safe}"
        path.write_bytes(data)
        kind = mimetypes.guess_type(safe)[0] or "application/octet-stream"
        with self.db.transaction() as session:
            session.add(ChatFile(id=file_id, conversation=conversation, name=name, type=kind, path=str(path)))
        return {"id": file_id, "name": name, "type": kind, "size": len(data)}

    def file(self, conversation: str, file_id: str) -> ChatFile | None:
        """Le fichier, seulement s'il appartient bien à cette conversation."""
        with self.db.read() as session:
            return session.scalar(select(ChatFile).where(ChatFile.id == file_id,
                                                         ChatFile.conversation == conversation))
