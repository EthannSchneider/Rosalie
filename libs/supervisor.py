"""Superviseur : le processus indépendant qui lance Rosalie, la relance si elle tombe, et applique
les mises à jour demandées (python bot.py supervise).

Il reste en vie pendant que Rosalie redémarre : c'est lui qui déploie la version fusionnée, et
qui revient à la précédente si elle ne démarre pas. Il n'utilise que la bibliothèque standard
(et git) et ne charge pas le reste du code de Rosalie : une mise à jour cassée ne peut pas le
casser. (Lui-même n'est remplacé par une nouvelle version qu'à son propre redémarrage.)

Échanges, dans storages/evolve/ :
  update-request.json   écrit par Rosalie (libs/evolve/service.py) : « applique ce commit »
  supervisor.json       écrit ici : battement, version qui tourne, état de la mise à jour, historique

Une mise à jour :
  1. vérifie sur GitHub que la pull request est fusionnée et que le commit demandé est bien son
     commit de fusion ; récupère la branche de référence et vérifie qu'elle contient ce commit ;
  2. refuse si l'installation a des modifications locales non commitées (rien n'est touché) ;
  3. arrête Rosalie, sauvegarde ses bases SQLite, avance le code jusqu'au commit (fast-forward) ;
  4. installe les dépendances si requirements.txt a changé, reconstruit le site si webui/ a changé
     (les migrations de base s'appliquent toutes seules au démarrage) ;
  5. redémarre Rosalie et vérifie qu'elle répond (GET /api/v1/health) et reste en vie ;
  6. en cas d'échec : revient au commit précédent, restaure les bases, réinstalle, redémarre.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STATE_DIR = "evolve"
REQUEST_FILE = "update-request.json"
SUPERVISOR_FILE = "supervisor.json"
HEARTBEAT_EVERY = 10
DEFAULTS = {"evolve_repo": "EthannSchneider/Rosalie", "evolve_base_branch": "main", "github_token": ""}


class UpdateError(Exception):
    """La mise à jour ne peut pas se faire : message enregistré (et montré aux superadmins)."""


class Supervisor:
    def __init__(self, root: Path, storage: Path, *, command: list[str] | None = None,
                 remote: str | None = None, pull_info=None, healthy=None, log=None,
                 poll: float = 2, stop_timeout: float = 30, health_timeout: float = 120,
                 stable_for: float = 15):
        self.root = root
        self.storage = storage
        self.state_dir = storage / STATE_DIR
        self.command = command or [sys.executable, "bot.py", "rosalie"]
        self.remote = remote                  # tests : dépôt local à la place de GitHub
        self.pull_info = pull_info or self.__github_pull
        self.healthy = healthy or self.__healthy
        self.log = log or (lambda text: print(f"[superviseur] {text}", flush=True))
        self.poll = poll
        self.stop_timeout = stop_timeout
        self.health_timeout = health_timeout
        self.stable_for = stable_for
        self.child: subprocess.Popen | None = None
        self.stopping = False
        self.state: dict = self.__load_state()

    # --- boucle principale --------------------------------------------------------------------
    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.__on_signal)
        signal.signal(signal.SIGINT, self.__on_signal)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"démarre Rosalie ({' '.join(self.command)}), version {self.version()[:10] or 'inconnue'}")
        self.start_child()
        backoff, beat = 5.0, 0.0
        try:
            while not self.stopping:
                if time.monotonic() - beat >= HEARTBEAT_EVERY:
                    beat = time.monotonic()
                    self.save_state()
                request = self.take_request()
                if request is not None:
                    self.update(request)
                    backoff = 5.0
                elif self.child is not None and self.child.poll() is not None:
                    code = self.child.returncode
                    if code == 0:
                        self.log("Rosalie s'est arrêtée normalement : le superviseur s'arrête aussi")
                        return 0
                    self.log(f"Rosalie est tombée (code {code}) : relance dans {backoff:.0f} s")
                    self.__sleep(backoff)
                    backoff = min(backoff * 2, 60)
                    if not self.stopping:
                        self.start_child()
                self.__sleep(self.poll)
        finally:
            self.stop_child()
            self.state["heartbeat"] = 0
            self.save_state(beat=False)
        return 0

    def __on_signal(self, *_):
        self.stopping = True

    def __sleep(self, seconds: float):
        end = time.monotonic() + seconds
        while not self.stopping and time.monotonic() < end:
            time.sleep(min(0.5, seconds))

    # --- Rosalie (processus enfant) -----------------------------------------------------------
    def start_child(self):
        self.child = subprocess.Popen(self.command, cwd=self.root)

    def stop_child(self):
        child, self.child = self.child, None
        if child is None or child.poll() is not None:
            return
        # SIGINT d'abord : comme Ctrl+C, Rosalie ferme ses interfaces et ses bases proprement
        for send, patience in ((lambda: child.send_signal(signal.SIGINT), self.stop_timeout),
                               (child.terminate, 10)):
            send()
            try:
                child.wait(patience)
                return
            except subprocess.TimeoutExpired:
                continue
        self.log("Rosalie ne s'arrête pas : arrêt forcé")
        child.kill()
        child.wait()

    def __healthy(self) -> bool:
        """Rosalie répond-elle ? (site web, toujours lancé par python bot.py)"""
        host = os.getenv("WEB_UI_HOST", "127.0.0.1").strip() or "127.0.0.1"
        host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        port = os.getenv("WEB_UI_PORT", "8765") or "8765"
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/api/v1/health", timeout=5) as response:
                return response.status == 200 and json.loads(response.read().decode()).get("ok") is True
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def wait_healthy(self) -> bool:
        """Elle doit répondre avant health_timeout, puis rester en vie stable_for secondes."""
        deadline = time.monotonic() + self.health_timeout
        while time.monotonic() < deadline:
            if self.child is None or self.child.poll() is not None:
                return False
            if self.healthy():
                break
            time.sleep(min(1, self.poll))
        else:
            return False
        end = time.monotonic() + self.stable_for
        while time.monotonic() < end:
            if self.child.poll() is not None:
                return False
            time.sleep(min(1, self.poll))
        return self.healthy()

    # --- état ---------------------------------------------------------------------------------
    def __load_state(self) -> dict:
        try:
            state = json.loads((self.state_dir / SUPERVISOR_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        return {"update": state.get("update"), "history": state.get("history", [])}

    def save_state(self, beat: bool = True):
        self.state.update({"pid": os.getpid(), "version": self.version()})
        if beat:
            self.state["heartbeat"] = time.time()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_dir / f"{SUPERVISOR_FILE}.tmp"
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, self.state_dir / SUPERVISOR_FILE)   # jamais de fichier à moitié écrit

    def progress(self, status: str, message: str, **fields):
        self.state["update"] = {**(self.state.get("update") or {}), "status": status,
                                "message": message, "at": time.time(), **fields}
        self.log(f"mise à jour : {message}")
        self.save_state()

    def take_request(self) -> dict | None:
        path = self.state_dir / REQUEST_FILE
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        path.unlink(missing_ok=True)
        try:
            request = json.loads(raw)
            if not (isinstance(request.get("operation"), int) and isinstance(request.get("pull"), int)
                    and isinstance(request.get("sha"), str) and len(request["sha"]) >= 40
                    and all(c in "0123456789abcdef" for c in request["sha"])):
                raise ValueError("champs manquants")
        except (ValueError, AttributeError) as error:
            self.log(f"demande de mise à jour illisible, ignorée ({error})")
            return None
        return request

    def setting(self, key: str) -> str:
        """Un réglage de Rosalie, lu directement dans storages/config.sqlite3."""
        try:
            db = sqlite3.connect(f"file:{self.storage / 'config.sqlite3'}?mode=ro", uri=True, timeout=5)
            try:
                row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            finally:
                db.close()
            value = json.loads(row[0]) if row else None
        except (sqlite3.Error, ValueError, TypeError):
            value = None
        return value if isinstance(value, str) and value else DEFAULTS[key]

    # --- git ----------------------------------------------------------------------------------
    def git(self, *args: str, check: bool = True, auth: bool = False) -> str:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        token = self.setting("github_token") if auth else ""
        if token:   # jeton en en-tête, par l'environnement : jamais dans la ligne de commande
            basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            env.update({"GIT_CONFIG_COUNT": "1",
                        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"})
        try:
            done = subprocess.run(["git", *args], cwd=self.root, env=env, capture_output=True,
                                  text=True, errors="replace", timeout=600)
        except (OSError, subprocess.SubprocessError) as error:
            raise UpdateError(f"git {args[0]} impossible : {type(error).__name__}") from None
        if check and done.returncode != 0:
            raise UpdateError(f"git {args[0]} a échoué : {(done.stderr or done.stdout).strip()[-400:]}")
        return done.stdout.strip()

    def version(self) -> str:
        try:
            return self.git("rev-parse", "HEAD")
        except UpdateError:
            return ""

    def __github_pull(self, repo: str, number: int) -> dict:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "rosalie-supervisor"}
        token = self.setting("github_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(f"https://api.github.com/repos/{repo}/pulls/{number}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise UpdateError(f"GitHub a refusé de montrer la pull request (HTTP {error.code})") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise UpdateError(f"GitHub injoignable : {type(error).__name__}") from None

    # --- mise à jour --------------------------------------------------------------------------
    def update(self, request: dict):
        sha = request["sha"]
        self.state["update"] = {"id": request.get("id"), "operation": request["operation"],
                                "pull": request["pull"], "requested_by": request.get("by", ""),
                                "target": sha, "started": time.time()}
        previous = ""
        touched = False
        try:
            self.progress("updating", "vérifie la pull request et l'installation")
            previous = self.__precheck(request)
            self.state["update"]["previous"] = previous
            self.progress("updating", "arrête Rosalie et sauvegarde ses données")
            self.stop_child()
            touched = True
            self.__backup()
            self.progress("updating", f"déploie la version {sha[:10]}")
            self.git("merge", "--ff-only", sha)
            self.__prepare(previous, sha)
            self.progress("restarting", "redémarre Rosalie")
            self.start_child()
            self.progress("restarting", "vérifie que Rosalie fonctionne")
            if not self.wait_healthy():
                raise UpdateError("Rosalie ne répond pas après le redémarrage")
            self.progress("done", f"version {sha[:10]} appliquée", deployed=sha, finished=time.time())
        except Exception as error:   # y compris une panne imprévue : on ne laisse jamais Rosalie arrêtée
            reason = str(error) if isinstance(error, UpdateError) else f"{type(error).__name__} : {error}"
            self.log(f"mise à jour en échec : {reason}")
            if touched:
                reason += " — " + self.__rollback(previous, sha)
            self.progress("failed", reason, finished=time.time())
        self.state["history"] = [*self.state.get("history", []), dict(self.state["update"])][-50:]
        self.save_state()

    def __precheck(self, request: dict) -> str:
        """Tout ce qui se vérifie SANS toucher à l'installation. Retourne le commit actuel."""
        repo, base = self.setting("evolve_repo"), self.setting("evolve_base_branch")
        if request.get("repo") != repo or request.get("base") != base:
            raise UpdateError("la demande ne correspond pas au dépôt configuré")
        sha = request["sha"]
        pull = self.pull_info(repo, request["pull"])
        if not pull.get("merged"):
            raise UpdateError(f"la pull request #{request['pull']} n'est pas fusionnée")
        if pull.get("merge_commit_sha") != sha or (pull.get("base") or {}).get("ref") != base:
            raise UpdateError("le commit demandé n'est pas le commit de fusion de cette pull request")
        previous = self.git("rev-parse", "HEAD")
        if self.git("status", "--porcelain", "--untracked-files=no"):
            raise UpdateError("l'installation a des modifications locales non commitées : "
                              "mise à jour refusée pour ne rien écraser")
        self.git("fetch", "--no-tags", self.remote or f"https://github.com/{repo}.git", base, auth=True)
        if subprocess.run(["git", "merge-base", "--is-ancestor", sha, "FETCH_HEAD"], cwd=self.root,
                          capture_output=True).returncode != 0:
            raise UpdateError(f"la branche {base} ne contient pas le commit de fusion")
        if subprocess.run(["git", "merge-base", "--is-ancestor", previous, sha], cwd=self.root,
                          capture_output=True).returncode != 0:
            raise UpdateError("l'installation a divergé de la branche de référence (commits locaux) : "
                              "mets-la à jour à la main")
        return previous

    def __prepare(self, old: str, new: str):
        """Dépendances et étapes de préparation, selon ce qui a changé entre deux versions."""
        changed = self.git("diff", "--name-only", old, new).splitlines()
        if "requirements.txt" in changed:
            self.progress(self.state["update"]["status"], "installe les dépendances Python")
            self.__run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r",
                        "requirements.txt"], "installation des dépendances")
        if any(name.startswith("webui/") for name in changed):
            if shutil.which("npm") is None:
                self.log("webui/ a changé mais npm est introuvable : le site reste dans sa version construite")
                self.state["update"]["warning"] = "site non reconstruit (npm introuvable)"
            else:
                self.progress(self.state["update"]["status"], "reconstruit le site")
                self.__run(["npm", "--prefix", "webui", "ci", "--no-audit", "--no-fund"], "npm ci")
                self.__run(["npm", "--prefix", "webui", "run", "build"], "construction du site")

    def __run(self, command: list[str], what: str):
        try:
            done = subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                                  errors="replace", timeout=1800)
        except (OSError, subprocess.SubprocessError) as error:
            raise UpdateError(f"{what} : {type(error).__name__}") from None
        if done.returncode != 0:
            raise UpdateError(f"{what} en échec : {(done.stderr or done.stdout).strip()[-400:]}")

    def __backup(self):
        """Copie des bases SQLite (Rosalie arrêtée) : une migration ne se défait pas toute seule."""
        target = self.state_dir / "backup"
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        for path in self.storage.glob("*.sqlite3*"):
            if path.is_file():
                shutil.copy2(path, target / path.name)

    def __restore(self):
        source = self.state_dir / "backup"
        if not source.is_dir():
            return
        for path in self.storage.glob("*.sqlite3*"):   # -wal / -shm de la nouvelle version compris
            if path.is_file():
                path.unlink()
        for path in source.iterdir():
            shutil.copy2(path, self.storage / path.name)

    def __rollback(self, previous: str, failed: str) -> str:
        """Retour à la version précédente. Retourne ce qui s'est passé (pour l'historique)."""
        self.progress(self.state["update"]["status"], f"retour à la version précédente ({previous[:10]})")
        try:
            self.stop_child()
            if self.git("rev-parse", "HEAD") != previous:
                self.git("reset", "--hard", previous)   # sûr : aucune modification locale (vérifié avant)
                self.__prepare(failed, previous)
            self.__restore()
            self.start_child()
            if self.wait_healthy():
                self.state["update"]["rolled_back"] = True
                return f"version précédente ({previous[:10]}) restaurée, Rosalie fonctionne"
            self.state["update"]["rolled_back"] = False
            return (f"version précédente ({previous[:10]}) restaurée mais Rosalie ne répond pas : "
                    "intervention manuelle nécessaire")
        except Exception as error:
            self.state["update"]["rolled_back"] = False
            if self.child is None:
                self.start_child()
            return f"le retour à la version précédente a échoué ({error}) : intervention manuelle nécessaire"
