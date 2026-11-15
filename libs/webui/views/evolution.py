"""Vues JSON : évolution du code (opérations, état du superviseur). Jamais de secret."""
from __future__ import annotations

from libs.models.evolution import DEPLOY, REASONS, WORK, Evolution


def operation_json(operation: Evolution) -> dict:
    return {"id": operation.id, "title": operation.title, "reason": operation.reason,
            "reason_label": REASONS.get(operation.reason, operation.reason),
            "brief": operation.brief, "author": operation.author, "status": operation.status,
            "detail": operation.detail, "branch": operation.branch,
            "pr_number": operation.pr_number, "pr_url": operation.pr_url,
            "base_sha": operation.base_sha, "head_sha": operation.head_sha,
            "merged_sha": operation.merged_sha, "previous_sha": operation.previous_sha,
            "deployed_sha": operation.deployed_sha, "checks": operation.checks,
            "checks_ok": operation.checks_ok, "summary": operation.summary, "error": operation.error,
            "events": operation.events, "created": operation.created, "updated": operation.updated,
            "working": operation.status in WORK, "deploying": operation.status in DEPLOY}


def evolution_json(evolver, operations: list[Evolution], notice: str = "") -> dict:
    config = evolver.config
    supervisor = evolver.supervisor()
    return {"enabled": config.evolve, "repo": config.evolve_repo, "base": config.evolve_base_branch,
            "code_model": config.code_model, "problems": evolver.problems(),
            "supervised": evolver.supervised(),
            "version": supervisor.get("version") or evolver.version(),
            "busy": any(o.status in (*WORK, *DEPLOY) for o in operations),
            "reasons": [{"name": name, "label": label} for name, label in REASONS.items()],
            "notice": notice,
            "operations": [operation_json(operation) for operation in operations]}
