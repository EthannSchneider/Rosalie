"""Outils propres à Discord (proposés au modèle seulement si l'interface Discord tourne) :

  server.py      infos serveur/membre, salons, membres, rôles, invitations, fils, statut
  messages.py    envoyer, lire, chercher, réagir, épingler, modifier, supprimer, sondages
  moderation.py  rôles, surnoms, exclusion temporaire, kick, ban
"""
from interfaces.discord.tools import server, messages, moderation  # noqa: F401
