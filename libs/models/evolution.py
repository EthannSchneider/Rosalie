"""Modèle : les opérations d'évolution du code (table evolutions de storages/rosalie.sqlite3).

Une opération = une demande de modification du code de Rosalie, de l'analyse jusqu'à la mise à
jour : qui l'a demandée, pourquoi, où elle en est, sa pull request, les versions (commits)
avant / après, et le journal de ce qui s'est passé. C'est l'historique affiché sur le site.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from libs.config.schema import SettingError
from libs.db import Database
from libs.models.bases import MainBase

# Étapes, dans l'ordre. « pr_open » = pull request ouverte, en attente de fusion.
WORK = ("analysis", "editing", "testing")           # le modèle de code travaille
DEPLOY = ("updating", "restarting")                 # mise à jour en cours (superviseur)
STATUSES = (*WORK, "pr_open", "merged", *DEPLOY, "done", "failed", "closed", "update_failed")
REASONS = {"security": "Faille de sécurité", "feature": "Nouvelle fonctionnalité",
           "capability": "Capacité manquante", "bug": "Bug ou fiabilité"}


class Evolution(MainBase):
    __tablename__ = "evolutions"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)                 # clé de REASONS
    brief: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    author: Mapped[str] = mapped_column(Text, nullable=False)                 # qui l'a demandée
    conversation: Mapped[str | None] = mapped_column(Text)                    # où prévenir (clé)
    status: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")     # activité en cours
    branch: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pr_number: Mapped[int | None] = mapped_column(Integer)
    pr_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    base_sha: Mapped[str] = mapped_column(Text, nullable=False, default="")       # départ de la branche
    head_sha: Mapped[str] = mapped_column(Text, nullable=False, default="")       # commit poussé
    merged_sha: Mapped[str] = mapped_column(Text, nullable=False, default="")     # commit de fusion
    previous_sha: Mapped[str] = mapped_column(Text, nullable=False, default="")   # version avant mise à jour
    deployed_sha: Mapped[str] = mapped_column(Text, nullable=False, default="")   # version appliquée
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    checks_ok: Mapped[bool | None] = mapped_column(Boolean)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created: Mapped[float] = mapped_column(Float, nullable=False)
    updated: Mapped[float] = mapped_column(Float, nullable=False)


class Evolutions:
    """Dépôt des opérations. Les opérations incompatibles sont refusées ici, dans une seule
    transaction : une seule modification en cours à la fois, aucune pendant une mise à jour."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, operation_id: int) -> Evolution | None:
        with self.db.read() as session:
            return session.get(Evolution, operation_id)

    def require(self, operation_id: int) -> Evolution:
        operation = self.get(operation_id)
        if operation is None:
            raise SettingError(f"opération #{operation_id} inconnue")
        return operation

    def recent(self, limit: int = 50) -> list[Evolution]:
        with self.db.read() as session:
            return list(session.scalars(select(Evolution).order_by(Evolution.id.desc()).limit(limit)))

    def with_status(self, *statuses: str) -> list[Evolution]:
        with self.db.read() as session:
            return list(session.scalars(select(Evolution).where(Evolution.status.in_(statuses))
                                        .order_by(Evolution.id)))

    def create(self, *, title: str, reason: str, brief: dict, author: str,
               conversation: str | None) -> Evolution:
        now = time.time()
        operation = Evolution(title=title, reason=reason, brief=brief, author=author,
                              conversation=conversation, status="analysis", created=now, updated=now,
                              events=[_event("analysis", "Demande reçue", author, now)])
        with self.db.transaction() as session:
            _refuse_if_busy(session)
            session.add(operation)
        return operation

    def begin_update(self, operation_id: int, by: str) -> Evolution:
        """Passe l'opération en « mise à jour », seulement si rien d'incompatible n'est en cours."""
        with self.db.transaction() as session:
            _refuse_if_busy(session)
            operation = session.get(Evolution, operation_id)
            if operation is None:
                raise SettingError(f"opération #{operation_id} inconnue")
            if operation.status not in ("merged", "update_failed"):
                raise SettingError("la pull request doit d'abord être fusionnée")
            _apply(operation, "updating", "Mise à jour demandée", by, {"error": ""})
        return operation

    def update(self, operation_id: int, status: str | None = None, message: str = "",
               by: str = "", **fields) -> Evolution | None:
        """Change des champs ; un changement d'étape (ou un message) s'ajoute au journal."""
        with self.db.transaction() as session:
            operation = session.get(Evolution, operation_id)
            if operation is None:
                return None
            _apply(operation, status, message, by, fields)
        return operation


def _refuse_if_busy(session):
    busy = session.scalars(select(Evolution).where(Evolution.status.in_((*WORK, *DEPLOY)))).first()
    if busy is None:
        return
    what = "une mise à jour" if busy.status in DEPLOY else "une modification du code"
    raise SettingError(f"{what} est déjà en cours (opération #{busy.id} : {busy.title}) : "
                       "attends qu'elle se termine")


def _apply(operation: Evolution, status: str | None, message: str, by: str, fields: dict):
    now = time.time()
    for key, value in fields.items():
        setattr(operation, key, value)
    if status is not None and status not in STATUSES:
        raise ValueError(f"étape inconnue : {status}")
    changed = status is not None and status != operation.status
    if changed:
        operation.status = status
    if changed or message:
        # nouvel objet : l'ORM voit le changement
        operation.events = [*operation.events, _event(operation.status, message, by, now)][-200:]
    operation.updated = now


def _event(status: str, message: str, by: str, at: float) -> dict:
    return {"at": at, "status": status, "message": message, "by": by}
