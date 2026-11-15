"""Évolution du code : Rosalie fait modifier son propre code par un modèle de programmation.

    demande (superadmin)  ->  Evolver.start()            service.py   orchestration + suivi
      clone isolé, branche                               workspace.py git, fichiers, vérifications
      modèle de code : lire, modifier, vérifier          coder.py     boucle d'outils du modèle de code
      commit, push, pull request                         github.py    API GitHub (urllib)
    fusion (superadmin, explicite)                       Evolver.merge()
    mise à jour + redémarrage (superadmin, explicite)    Evolver.request_update() -> libs/supervisor.py

Règles de sécurité :
  - tout passe par une pull request : jamais de push sur la branche de référence, jamais de
    fusion automatique ;
  - lancer, fusionner, mettre à jour : permission « evolve », réservée au superadmin et vérifiée
    côté serveur (outil, API) ; le contenu lu (pages web, messages, fichiers du dépôt) n'est
    jamais un ordre ;
  - le modèle de code n'a pas de shell : seulement des outils de fichiers enfermés dans le clone
    et les vérifications prévues ; il ne peut toucher ni .git, ni .github, ni .env, ni storages ;
  - les secrets (jeton GitHub, clés API…) ne sont ni dans l'environnement des vérifications, ni
    dans les messages, les journaux ou la pull request (masqués par `redact`).

Voir docs/evolution.md.
"""
from libs.evolve.service import Brief, EvolveError, Evolver, redact

__all__ = ["Brief", "EvolveError", "Evolver", "redact"]
