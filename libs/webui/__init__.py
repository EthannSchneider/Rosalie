"""Le site de Rosalie : backend MVC + interface React (webui/). Les modèles de données sont
partagés avec le reste de Rosalie : libs/models/.

  views/        forme des réponses JSON
  controllers/  logique par domaine (session, compte, réglages, comptes, chat)
  api/v1.py     table des routes /api/v1/… et leurs droits
  router.py · http.py · security.py · events.py · server.py   plomberie HTTP

  python bot.py           le site démarre avec Rosalie (avec Discord)
  python bot.py web       seulement le site (réglages, comptes ; pas de chat)
"""
from libs.webui.server import WebServer

__all__ = ["WebServer"]
