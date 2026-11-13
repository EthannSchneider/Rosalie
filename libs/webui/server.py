"""Serveur HTTP du site (bibliothèque standard, dans des fils) : uniquement la plomberie.

    requête -> sécurité (security.py) -> routeur (api/v1.py) -> droits -> contrôleur
            -> réponse (Json | Stream | File, http.py) ; le reste sert webui/dist (React).

L'organisation MVC : modèles (models/), vues JSON (views/), contrôleurs (controllers/), table
des routes versionnée (api/v1.py). Voir docs/site-web.md.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, unquote, urlsplit

from libs.config import ROOT_DIR, storage_dir
from libs.config.schema import SettingError
from libs.config.store import ConfigStore
from libs.log import Log
from libs.webui.api import v1
from libs.webui.http import File, HttpError, Json, Request, Stream
from libs.models import Accounts, main_database
from libs.webui.router import authorize
from libs.webui.security import Throttle, check_origin, is_loopback, session_token

if TYPE_CHECKING:
    from interfaces.web import WebInterface

DIST_DIR = ROOT_DIR / "webui" / "dist"
MAX_BODY = 1_000_000          # une personnalité fait quelques Ko

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Rosalie</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem">
<h1>Interface pas encore construite</h1>
<p>Le serveur fonctionne, mais il manque l'interface web. Depuis la racine du projet :</p>
<pre>npm --prefix webui install
npm --prefix webui run build</pre>
<p>Puis recharge cette page. (Ou utilise <code>python bot.py settings</code>.)</p></body>"""


class WebServer:
    def __init__(self, store: ConfigStore, host: str = "127.0.0.1", port: int = 8765, *,
                 storage: Path | None = None, chat: WebInterface | None = None,
                 dist: Path = DIST_DIR, accounts: Accounts | None = None):
        self.store = store
        self.chat = chat
        self.dist = dist
        self.local = is_loopback(host)
        self.__own_accounts = accounts is None   # sinon : ceux de Rosalie, fermés par elle
        self.accounts = accounts or Accounts(main_database(storage or storage_dir()))
        self.throttle = Throttle()
        self.closing = threading.Event()
        self.router, self.controllers = v1.build(self)
        server = self

        class Handler(_Handler):
            app = server

        self.http = ThreadingHTTPServer((host, port), Handler)
        self.http.daemon_threads = True

    @property
    def url(self) -> str:
        host, port = self.http.server_address[:2]
        host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        return f"http://{host}:{port}"

    def start(self) -> "WebServer":
        threading.Thread(target=self.http.serve_forever, name="webui", daemon=True).start()
        return self

    def serve_forever(self):
        self.http.serve_forever()

    def stop(self):
        self.closing.set()
        self.http.shutdown()
        self.http.server_close()
        if self.__own_accounts:
            self.accounts.close()

    def announce_setup(self):
        """Premier lancement : affiche le code pour créer le compte superadmin."""
        code = self.accounts.setup_code
        if not code:
            return
        text = (f"Aucun compte sur le site : ouvre {self.url} et crée le superadmin avec le code "
                f"d'installation {code} (ou : python bot.py users add <nom> --role superadmin)")
        Log.warning(text)
        if os.getenv("LOG_QUIET"):   # interface terminal : le log ne s'affiche pas
            print(f"\n🔑 {text}\n", file=sys.stderr)


class _Handler(BaseHTTPRequestHandler):
    app: WebServer
    server_version = "Rosalie"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):   # noqa: A002 — pas de bruit dans la console
        pass

    def do_GET(self):
        self.__handle("GET")

    def do_POST(self):
        self.__handle("POST")

    def do_PUT(self):
        self.__handle("PUT")

    def do_PATCH(self):
        self.__handle("PATCH")

    def do_DELETE(self):
        self.__handle("DELETE")

    # --- routage ------------------------------------------------------------------------------
    def __handle(self, method: str):
        url = urlsplit(self.path)
        app = self.app
        try:
            check_origin(method, self.headers, app.local)
            if url.path == "/api" or url.path.startswith("/api/"):
                if not app.router.owns(url.path):
                    raise HttpError(404, "version d'API inconnue (actuelle : /api/v1)")
                route, params = app.router.resolve(method, url.path)
                token = session_token(self.headers)
                request = Request(method, url.path, params,
                                  {k: v[0] for k, v in parse_qs(url.query).items()},
                                  self.__body() if method in ("POST", "PUT", "PATCH") else None,
                                  app.accounts.session_user(token), token, self.client_address[0])
                authorize(route, request)
                response = route.handler(request)
            elif method == "GET":
                return self.__static(url.path)
            else:
                raise HttpError(405, "méthode non permise")
        except HttpError as error:
            response = Json({"error": str(error)}, error.status)
        except SettingError as error:
            response = Json({"error": str(error)}, 400)
        except ValueError as error:
            response = Json({"error": f"requête invalide : {error}"}, 400)
        except Exception as error:
            Log.error(f"Site web : {type(error).__name__} : {error}")
            response = Json({"error": "erreur interne (voir le log)"}, 500)
        self.__respond(response)

    def __body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise HttpError(413, "requête trop grosse")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    # --- réponses -------------------------------------------------------------------------------
    def __respond(self, response):
        if isinstance(response, Stream):
            return self.__stream(response)
        if isinstance(response, File):
            return self.__file(response)
        data = json.dumps(response.data, ensure_ascii=False).encode("utf-8")
        self.send_response(response.status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.__security_headers()
        self.end_headers()
        self.wfile.write(data)

    def __stream(self, stream: Stream):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.__security_headers()
        self.end_headers()
        self.close_connection = True
        try:
            for chunk in stream.events:
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            stream.close()

    def __file(self, file: File):
        if not file.path.is_file():
            return self.__respond(Json({"error": "fichier introuvable"}, 404))
        data = file.path.read_bytes()
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in file.name) or "fichier"
        self.send_response(200)
        self.send_header("Content-Type", file.content_type if file.inline else "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'{"inline" if file.inline else "attachment"}; filename="{safe}"')
        self.send_header("Cache-Control", "private, max-age=86400")
        self.__security_headers()
        self.end_headers()
        self.wfile.write(data)

    def __static(self, path: str):
        """Fichiers de l'interface React ; toute autre adresse renvoie index.html (routes du
        navigateur : /chat, /settings/…)."""
        dist = self.app.dist.resolve()
        target = (dist / unquote(path).lstrip("/")).resolve()
        if not target.is_relative_to(dist) or not target.is_file():
            target = dist / "index.html"
        if not target.is_file():
            data, kind = NOT_BUILT.encode("utf-8"), "text/html; charset=utf-8"
        else:
            data = target.read_bytes()
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
                kind += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if target.name == "index.html" else "max-age=31536000, immutable")
        self.__security_headers()
        self.end_headers()
        self.wfile.write(data)

    def __security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "frame-ancestors 'none'")
