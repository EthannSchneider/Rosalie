"""Orchestration d'une évolution du code, et son suivi.

    start()            demande -> clone -> opencode dans un conteneur -> vérifications -> push -> PR
    resume()           au démarrage : reprend le suivi d'un opencode qui tourne encore
    refresh()          où en est la pull request sur GitHub (fusionnée ? fermée ?)
    merge()            fusion, sur action explicite d'un superadmin
    request_update()   demande de mise à jour + redémarrage au superviseur (libs/supervisor.py)
    sync()             reporte dans l'historique ce que le superviseur a fait

Les droits (permission « evolve ») sont vérifiés par les appelants : l'outil (permissions.py) et
l'API (api/v1.py). Ici : les règles de cohérence (rien de concurrent, PR fusionnée avant mise à
jour) et la discipline sur les secrets (`redact` sur tout texte qui sort).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
import traceback
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from libs.config import ROOT_DIR
from libs.config.schema import SettingError
from libs.core.types import split_key
from libs.containers import ContainerError, Limits
from libs.evolve.github import GitHub, GitHubError
from libs.evolve.opencode import CoderResult, OpenCode
from libs.evolve.sandbox import KIND as SANDBOX_KIND, WORKDIR, Sandbox, container_name
from libs.evolve.workspace import BRANCH_PREFIX, CheckResult, Workspace, WorkspaceError
from libs.log import Log
from libs.models.evolution import DEPLOY, REASONS, WORK, Evolution, Evolutions

if TYPE_CHECKING:
    from libs.core.rosalie import Rosalie

STATE_DIR = "evolve"                    # storages/evolve/ : échanges avec le superviseur
REQUEST_FILE = "update-request.json"    # écrit par Rosalie, lu par le superviseur
SUPERVISOR_FILE = "supervisor.json"     # écrit par le superviseur
SUPERVISOR_ALIVE = 30                   # secondes sans battement : superviseur considéré absent
DEPLOY_LOST = 180                       # mise à jour sans nouvelles du superviseur : échec
FIELD_CHARS = 6000


class EvolveError(Exception):
    """Échec attendu d'une opération : le message (sans secret) est montré à l'auteur."""


@dataclass
class Brief:
    """Ce que le modèle principal (ou le superadmin, sur le site) transmet au modèle de code."""
    title: str
    reason: str               # security | feature | capability | bug
    objective: str
    context: str = ""
    constraints: str = ""
    criteria: str = ""        # critères de réussite

    def validated(self) -> "Brief":
        clean = Brief(**{key: str(value or "").strip()[:FIELD_CHARS] for key, value in asdict(self).items()})
        clean.title = " ".join(clean.title.split())[:120]
        clean.reason = clean.reason.lower()
        if clean.reason not in REASONS:
            raise SettingError(f"raison inconnue « {self.reason} » ({', '.join(REASONS)})")
        if len(clean.title) < 4:
            raise SettingError("titre trop court")
        if len(clean.objective) < 10:
            raise SettingError("objectif manquant : décris précisément ce qui doit changer")
        return clean

    def text(self, author: str) -> str:
        parts = [f"# {self.title}", f"Raison : {REASONS[self.reason]}", f"Demandé par : {author}",
                 f"## Objectif\n{self.objective}"]
        if self.context:
            parts.append(f"## Contexte\n{self.context}")
        if self.constraints:
            parts.append(f"## Contraintes\n{self.constraints}")
        parts.append(f"## Critères de réussite\n{self.criteria or 'Les vérifications du projet passent.'}")
        return "\n\n".join(parts)


def redact(text: str, secrets: Iterable[str]) -> str:
    """Masque toute valeur secrète connue (et tout jeton GitHub reconnaissable) dans un texte."""
    for secret in sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True):
        text = text.replace(secret, "•••")
    return re.sub(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b", "•••", text)


class Evolver:
    poll = 4.0      # secondes entre deux coups d'œil sur opencode (tests : plus court)

    def __init__(self, rosalie: "Rosalie", *, github=None, remote: str | None = None, checks=None,
                 docker=None):
        self.rosalie = rosalie
        self.operations = Evolutions(rosalie.accounts.db)
        self.state_dir = rosalie.config.storage_dir / STATE_DIR
        self.__github = github          # tests : faux GitHub
        self.__remote = remote          # tests : dépôt local
        self.__checks = checks          # tests : vérifications légères
        self.__docker = docker          # tests : faux Docker
        self.__tasks: set[asyncio.Task] = set()
        self.__detached: set[int] = set()   # opérations dont opencode tourne seul dans son conteneur
        self.__version: str | None = None

    # --- état ---------------------------------------------------------------------------------
    @property
    def config(self):
        return self.rosalie.config

    def redact(self, text: str) -> str:
        return redact(str(text), self.config.secrets)

    def github(self) -> GitHub:
        return self.__github or GitHub(self.config.github_token)

    def docker(self):
        return self.__docker or getattr(self.rosalie, "docker", None)

    def version(self) -> str:
        """Commit de la version qui tourne (vide si l'installation n'est pas un dépôt git)."""
        if self.__version is None:
            try:
                self.__version = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT_DIR, capture_output=True, text=True,
                    timeout=5).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                self.__version = ""
        return self.__version

    def supervisor(self) -> dict:
        """Dernier état écrit par le superviseur ({} s'il n'a jamais tourné)."""
        try:
            return json.loads((self.state_dir / SUPERVISOR_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def supervised(self) -> bool:
        return time.time() - float(self.supervisor().get("heartbeat", 0)) < SUPERVISOR_ALIVE

    def problems(self) -> list[str]:
        """Ce qui empêche de lancer une modification (vide = prêt)."""
        config = self.config
        problems = []
        if not config.evolve:
            problems.append("l'évolution du code est désactivée (Réglages → Évolution du code)")
        if not config.github_token and self.__github is None:
            problems.append("le jeton GitHub n'est pas défini (Réglages → Évolution du code)")
        if not config.containers:
            problems.append("les conteneurs Docker sont désactivés : le modèle de code (opencode) "
                            "travaille dans un conteneur (Réglages → Conteneurs)")
        elif not config.containers_network:
            problems.append("opencode a besoin du réseau dans son conteneur "
                            "(Réglages → Conteneurs → Accès réseau)")
        elif self.docker() is None:
            problems.append("Docker n'est pas disponible ici")
        return problems

    # --- lancer une modification ----------------------------------------------------------
    def start(self, brief: Brief, author: str, conversation: str | None = None) -> Evolution:
        """Enregistre la demande et lance le travail en arrière-plan (dans la boucle asyncio).
        Refusé si une autre modification ou une mise à jour est en cours."""
        brief = brief.validated()
        problems = self.problems()
        if problems:
            raise SettingError(" ; ".join(problems))
        operation = self.operations.create(title=brief.title, reason=brief.reason, brief=asdict(brief),
                                           author=author, conversation=conversation)
        Log.command(f"Évolution #{operation.id} demandée par {author} : {brief.title}")
        self.__spawn(self.__work(operation.id, brief, author))
        return operation

    def __spawn(self, work):
        task = asyncio.get_running_loop().create_task(work)
        self.__tasks.add(task)
        task.add_done_callback(self.__tasks.discard)

    def __workspace(self, operation_id: int, home: Path | None = None) -> Workspace:
        config = self.config
        remote = self.__remote or f"https://github.com/{config.evolve_repo}.git"
        workspace = Workspace(remote, config.evolve_base_branch, config.github_token, self.__checks, home)
        # le modèle de code et les vérifications travaillent dans un conteneur
        workspace.sandbox = Sandbox(
            self.docker(), workspace.root, operation_id, image=config.evolve_image,
            limits=Limits.of(config), network=config.containers_network,
            on_line=lambda line: self.operations.update(
                operation_id, detail=self.redact(f"prépare l'image : {line}")[:200]))
        return workspace

    async def __work(self, operation_id: int, brief: Brief, author: str, workspace: Workspace | None = None):
        """workspace donné = reprise d'une opération dont opencode tourne encore dans son conteneur."""
        resumed = workspace is not None
        workspace = workspace or self.__workspace(operation_id)
        self.__detached.discard(operation_id)
        keep = False
        try:
            operation = await self.__run(operation_id, brief, author, workspace, resumed)
            await self.__notify(operation, f"🔧 Pull request ouverte pour « {operation.title} » : "
                                           f"{operation.pr_url}\n"
                                + ("Les vérifications passent. " if operation.checks_ok else
                                   "⚠️ Une vérification a échoué (détail dans la pull request). ")
                                + "Elle attend une relecture et une fusion.")
        except asyncio.CancelledError:
            if operation_id in self.__detached:   # opencode continue dans son conteneur
                keep = True
                self.operations.update(operation_id, message="Arrêt de Rosalie : opencode continue dans "
                                                             "son conteneur, reprise au redémarrage")
            else:
                self.operations.update(operation_id, "failed", "Interrompue (arrêt de Rosalie)",
                                       error="interrompue par l'arrêt de Rosalie", detail="")
            raise
        except (EvolveError, WorkspaceError, ContainerError, GitHubError, SettingError) as error:
            await self.__fail(operation_id, str(error))
        except Exception as error:   # panne du modèle (OllamaError), imprévu…
            Log.error(self.redact(f"Évolution #{operation_id} : {error}\n{traceback.format_exc()}"))
            await self.__fail(operation_id, f"{type(error).__name__} : {error}")
        finally:
            self.__detached.discard(operation_id)
            if not keep:
                if workspace.sandbox is not None:
                    await asyncio.shield(workspace.sandbox.close())
                await asyncio.to_thread(workspace.cleanup)

    async def __fail(self, operation_id: int, reason: str):
        reason = self.redact(reason)[:2000]
        operation = self.operations.update(operation_id, "failed", f"Échec : {reason}", error=reason, detail="")
        Log.warning(f"Évolution #{operation_id} en échec : {reason}")
        if operation is not None:
            await self.__notify(operation, f"⚠️ La modification « {operation.title} » a échoué : {reason}")

    async def __run(self, operation_id: int, brief: Brief, author: str, workspace: Workspace,
                    resumed: bool = False) -> Evolution:
        config = self.config
        operations = self.operations
        if resumed:
            branch = workspace.branch
            operations.update(operation_id, message="Reprise après le redémarrage de Rosalie")
        else:
            branch = f"{BRANCH_PREFIX}evolve-{operation_id}-{_slug(brief.title)}"
            operations.update(operation_id, detail="clone le dépôt", branch=branch)
            await asyncio.to_thread(workspace.prepare, branch)
            operations.update(operation_id, message=f"Dépôt cloné, branche {branch}", base_sha=workspace.base_sha)

        async def activity(status: str, detail: str):
            operations.update(operation_id, status, detail=self.redact(detail)[:200])

        if not resumed:
            operations.update(operation_id, detail="démarre le conteneur de travail")
            await workspace.sandbox.start()
            operations.update(operation_id, message=f"Conteneur de travail {workspace.sandbox.name} démarré")
        coder = OpenCode(workspace.sandbox, config, name=self.rosalie.name, on_activity=activity,
                         on_line=lambda line: operations.update(
                             operation_id, detail=self.redact(line)[:200]), poll=self.poll)
        self.__detached.add(operation_id)   # à partir d'ici, un arrêt de Rosalie ne l'interrompt pas
        result: CoderResult = await coder.run(brief.text(author))
        self.__detached.discard(operation_id)
        if not result.finished:
            raise EvolveError(f"le modèle de code ({config.code_model}) n'a pas terminé : "
                              f"{result.summary or 'raison inconnue'} — rien n'a été poussé")
        discarded = await asyncio.to_thread(workspace.discard_protected)
        if discarded:
            result.risks = (f"{result.risks}\n" if result.risks else "") + \
                "Modifications annulées (chemins protégés) : " + ", ".join(discarded[:20]) + "."
            operations.update(operation_id, message="Chemins protégés rétablis : " + ", ".join(discarded[:20]))
        changed = await asyncio.to_thread(workspace.changed_files)
        if not changed:
            raise EvolveError("le modèle de code n'a modifié aucun fichier"
                              + (f" : {result.summary[:500]}" if result.summary else ""))
        diff = await asyncio.to_thread(workspace.diff)
        if any(secret in diff for secret in config.secrets if len(secret) >= 6):
            raise EvolveError("la modification contient un secret des réglages : rien n'a été poussé")

        # Vérifications finales, toujours relancées sur l'état exact qui sera poussé
        operations.update(operation_id, "testing", detail="vérifications finales")
        checks = await workspace.run_checks(config.evolve_check_timeout)
        ok = all(check.ok is not False for check in checks)
        operations.update(operation_id, message="Vérifications : " + ("réussies" if ok else "EN ÉCHEC"),
                          checks=[{**check.as_dict(), "output": self.redact(check.output)} for check in checks],
                          checks_ok=ok, summary=self.redact(result.summary)[:FIELD_CHARS])

        title = self.redact(result.title or brief.title)[:120]
        operations.update(operation_id, detail="pousse la branche")
        head = await asyncio.to_thread(workspace.commit, f"{title}\n\nDemandé par {author} "
                                                         f"(évolution #{operation_id}).")
        await asyncio.to_thread(workspace.push)
        stat = await asyncio.to_thread(workspace.git, "show", "--stat", "--format=", "HEAD")
        body = self.redact(pull_request_body(brief, author, result, changed, stat.strip(), checks,
                                             config.code_model, operation_id))
        operations.update(operation_id, detail="ouvre la pull request", head_sha=head)
        pull = await asyncio.to_thread(
            self.github().create_pull, config.evolve_repo, title=title, head=branch,
            base=config.evolve_base_branch, body=body, draft=not ok)
        Log.command(f"Évolution #{operation_id} : pull request {pull.get('html_url')}")
        return operations.update(operation_id, "pr_open", "Pull request ouverte, en attente de fusion",
                                 pr_number=pull.get("number"), pr_url=pull.get("html_url", ""), detail="")

    # --- pull request -------------------------------------------------------------------------
    async def refresh(self, operation_id: int) -> Evolution:
        """Relit l'état de la pull request sur GitHub : fusionnée (ici ou sur GitHub) ? fermée ?"""
        operation = self.operations.require(operation_id)
        if operation.status not in ("pr_open", "merged", "update_failed") or not operation.pr_number:
            return operation
        pull = await asyncio.to_thread(self.github().pull, self.config.evolve_repo, operation.pr_number)
        if pull.get("merged") and pull.get("merge_commit_sha"):
            if operation.status == "pr_open" or operation.merged_sha != pull["merge_commit_sha"]:
                by = (pull.get("merged_by") or {}).get("login", "")
                operation = self.operations.update(
                    operation_id, "merged" if operation.status == "pr_open" else None,
                    f"Pull request fusionnée ({pull['merge_commit_sha'][:10]})", by,
                    merged_sha=pull["merge_commit_sha"])
        elif pull.get("state") == "closed" and operation.status == "pr_open":
            operation = self.operations.update(operation_id, "closed", "Pull request fermée sans fusion")
        return operation

    async def merge(self, operation_id: int, by: str) -> Evolution:
        """Fusionne la pull request (action explicite d'un superadmin, jamais automatique)."""
        operation = await self.refresh(operation_id)
        if operation.status == "merged":
            return operation
        if operation.status != "pr_open":
            raise SettingError("cette opération n'a pas de pull request en attente de fusion")
        if not operation.checks_ok:
            raise SettingError("une vérification a échoué : relis et fusionne sur GitHub si tu "
                               "l'assumes, je ne le fais pas d'ici")
        await asyncio.to_thread(self.github().merge_pull, self.config.evolve_repo, operation.pr_number,
                                sha=operation.head_sha)
        Log.command(f"Évolution #{operation_id} : pull request fusionnée par {by}")
        self.operations.update(operation_id, message="Fusion demandée", by=by)
        operation = await self.refresh(operation_id)
        if operation.status != "merged":
            raise SettingError("GitHub n'indique pas encore la fusion : réessaie dans un instant")
        return operation

    # --- mise à jour et redémarrage -----------------------------------------------------------
    async def request_update(self, operation_id: int, by: str) -> Evolution:
        """Demande au superviseur de déployer la version fusionnée et de redémarrer Rosalie."""
        operation = await self.refresh(operation_id)   # vérifie sur GitHub que c'est bien fusionné
        if operation.status not in ("merged", "update_failed") or not operation.merged_sha:
            raise SettingError("la pull request doit d'abord être fusionnée")
        if not self.supervised():
            raise SettingError("le superviseur ne tourne pas : lance Rosalie avec "
                               "« python bot.py supervise » pour pouvoir la mettre à jour d'ici")
        operation = self.operations.begin_update(operation_id, by)
        request = {"id": uuid.uuid4().hex, "operation": operation.id, "repo": self.config.evolve_repo,
                   "base": self.config.evolve_base_branch, "pull": operation.pr_number,
                   "sha": operation.merged_sha, "by": by, "at": time.time()}
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_dir / f"{REQUEST_FILE}.tmp"
        temporary.write_text(json.dumps(request), encoding="utf-8")
        os.replace(temporary, self.state_dir / REQUEST_FILE)
        Log.command(f"Évolution #{operation_id} : mise à jour vers {operation.merged_sha[:10]} demandée par {by}")
        return operation

    def sync(self) -> list[Evolution]:
        """Reporte l'avancement du superviseur sur l'opération en cours de mise à jour.
        Retourne les opérations qui viennent de se terminer (réussite ou échec)."""
        finished = []
        update = self.supervisor().get("update") or {}
        for operation in self.operations.with_status(*DEPLOY):
            if update.get("operation") == operation.id:
                status = update.get("status")
                fields = {"previous_sha": update.get("previous", ""), "detail": update.get("message", "")[:200]}
                if status == "done":
                    finished.append(self.operations.update(
                        operation.id, "done", f"Mise à jour réussie : version {update.get('deployed', '')[:10]}",
                        deployed_sha=update.get("deployed", ""), error="", **{**fields, "detail": ""}))
                elif status == "failed":
                    reason = self.redact(update.get("message", "mise à jour en échec"))[:2000]
                    finished.append(self.operations.update(
                        operation.id, "update_failed", f"Mise à jour en échec : {reason}", error=reason,
                        **{**fields, "detail": ""}))
                elif status in DEPLOY and (status != operation.status or fields["detail"] != operation.detail):
                    self.operations.update(operation.id, status, **fields)
            elif time.time() - operation.updated > DEPLOY_LOST and not self.supervised() \
                    and not (self.state_dir / REQUEST_FILE).exists():
                finished.append(self.operations.update(
                    operation.id, "update_failed", "Mise à jour sans nouvelles du superviseur",
                    error="le superviseur n'a pas traité la demande", detail=""))
        return [operation for operation in finished if operation is not None]

    async def resume(self, delay: float = 15):
        """Au démarrage : le suivi des modifications dont opencode tourne encore dans son conteneur
        reprend (les autres sont marquées en échec), et le résultat d'une mise à jour (réussie ou annulée) est annoncé à qui l'a demandée."""
        resumed = set()
        for operation in self.operations.with_status(*WORK):
            workspace = await self.__reattach(operation)
            if workspace is None:
                self.operations.update(operation.id, "failed", "Interrompue par un redémarrage de Rosalie",
                                       error="interrompue par un redémarrage", detail="")
                continue
            resumed.add(workspace.sandbox.name)
            Log.command(f"Évolution #{operation.id} : reprise, opencode tourne dans {workspace.sandbox.name}")
            self.__spawn(self.__work(operation.id, Brief(**operation.brief), operation.author, workspace))
        await self.__sweep(resumed)
        await asyncio.sleep(delay)   # le temps que les interfaces soient prêtes (et le superviseur)
        for operation in self.sync():
            if operation.status == "done":
                await self.__notify(operation, f"✅ Mise à jour faite : je tourne maintenant sur la version "
                                               f"{operation.deployed_sha[:10]} (« {operation.title} »).")
            else:
                await self.__notify(operation, f"⚠️ La mise à jour « {operation.title} » a échoué : "
                                               f"{operation.error}")

    async def __reattach(self, operation: Evolution) -> Workspace | None:
        """Le travail d'une opération interrompue par un redémarrage, s'il continue : opencode
        tourne encore dans son conteneur et le clone est toujours là. Sinon None."""
        config, docker = self.config, self.docker()
        if docker is None or not config.containers or not operation.branch:
            return None
        try:
            name = container_name(operation.id)
            state = await docker.managed(name)
            root = await docker.mount_source(name, WORKDIR)
            if state is None or state["status"] != "running" or root is None:
                return None
            workspace = self.__workspace(operation.id, root.parent)
            await asyncio.to_thread(workspace.reattach, operation.branch, operation.base_sha)
            return workspace
        except (ContainerError, WorkspaceError, OSError) as error:
            Log.warning(f"Évolution #{operation.id} : reprise impossible ({self.redact(str(error))})")
            return None

    async def __sweep(self, keep: set[str] = frozenset()):
        """Supprime les conteneurs de travail laissés par un arrêt brutal (sauf ceux des
        opérations reprises)."""
        docker = self.docker()
        if docker is None or not self.config.containers:
            return
        try:
            if await docker.problem():
                return
            for container in await docker.list(SANDBOX_KIND):
                if container["name"] not in keep:
                    await docker.remove(container["name"])
        except ContainerError as error:
            Log.warning(f"Évolution : conteneurs de travail non nettoyés ({error})")

    async def close(self):
        for task in list(self.__tasks):
            task.cancel()
        await asyncio.gather(*self.__tasks, return_exceptions=True)

    async def __notify(self, operation: Evolution, text: str):
        """Prévient dans la conversation d'où vient la demande (si son interface tourne)."""
        if not operation.conversation:
            return
        try:
            name, native_id = split_key(operation.conversation)
            interface = self.rosalie.interfaces.get(name)
            conversation = await interface.conversation(native_id) if interface else None
            if conversation is not None:
                await self.rosalie.send(conversation, self.redact(text), record=True)
        except Exception as error:   # prévenir ne doit jamais faire échouer l'opération
            Log.warning(f"Évolution #{operation.id} : message non envoyé ({type(error).__name__})")


def pull_request_body(brief: Brief, author: str, result: CoderResult, changed: list[str], stat: str,
                      checks: list[CheckResult], model: str, operation_id: int) -> str:
    """Texte de la pull request : pourquoi, quoi, vérifications, risques."""
    failed = [check for check in checks if check.ok is False]
    skipped = [check for check in checks if check.ok is None]
    lines = []
    if failed:
        lines += [f"> ⚠️ **Vérification en échec** : {', '.join(check.name for check in failed)}. "
                  "À corriger ou à assumer avant toute fusion.", ""]
    lines += ["## Pourquoi", f"**{REASONS[brief.reason]}** — demandé par {author} (évolution #{operation_id}).",
              "", brief.objective]
    if brief.context:
        lines += ["", "**Contexte**", brief.context]
    if brief.constraints:
        lines += ["", "**Contraintes**", brief.constraints]
    if brief.criteria:
        lines += ["", "**Critères de réussite**", brief.criteria]
    lines += ["", "## Modifications", result.summary or "(le modèle de code n'a pas donné de résumé)", "",
              f"{len(changed)} fichier(s) :", "```", stat or "\n".join(changed), "```",
              "", "## Vérifications"]
    if not checks:
        lines.append("Aucune vérification n'a été lancée.")
    for check in checks:
        mark = "✅" if check.ok else ("⚠️ non lancée" if check.ok is None else "❌ **échec**")
        lines.append(f"- {mark} {check.name} ({check.duration:.0f} s)"
                     + (f" — {check.output}" if check.ok is None and check.output else ""))
    for check in failed:
        lines += ["", f"<details><summary>Sortie de « {check.name} »</summary>", "", "```",
                  check.output.replace("```", "ʼʼʼ"), "```", "</details>"]
    lines += ["", "## Risques et limites", result.risks or "Aucun signalé par le modèle de code."]
    if skipped:
        lines.append(f"- Non vérifié sur la machine de Rosalie : {', '.join(check.name for check in skipped)}.")
    lines += ["- Rien n'est testé contre le vrai Discord ni contre les vrais fournisseurs de modèles.",
              "", "---",
              f"Écrit par le modèle de code de Rosalie (`{model}`, avec opencode, dans un conteneur "
              "Docker), à relire par un humain. "
              "Aucune fusion automatique."]
    return "\n".join(lines)


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-") or "change"
