"""Outils GÉNÉRIQUES de Rosalie (valables quelle que soit l'interface), un fichier par catégorie :

  base.py        socle : ToolContext, @tool, registre TOOLS, execute(), helpers
  initiative.py  say, relances programmées
  memory.py      souvenirs à long terme
  internet.py    recherche web, lecture de pages
  images.py      chercher et envoyer des photos
  utilities.py   météo

Les outils propres à une messagerie vivent dans interfaces/<nom>/tools/ (@tool(requires="<nom>")).
Ajouter un outil = une fonction async décorée par @tool dans le bon fichier (ou un nouveau
fichier, à importer ci-dessous). Un outil avec `confirm=` demande une confirmation à l'owner.
"""
from libs.assistant.tools.base import (GUEST_TOOLS, TOOLS, WEB_TOOLS, Tool, ToolContext, ToolError,
                                       execute, schemas, tool)
# Importer chaque catégorie enregistre ses outils dans TOOLS (dans cet ordre, montré au modèle)
from libs.assistant.tools import initiative, memory, internet, images, utilities  # noqa: F401,E402

__all__ = ["GUEST_TOOLS", "TOOLS", "WEB_TOOLS", "Tool", "ToolContext", "ToolError", "execute",
           "schemas", "tool"]
