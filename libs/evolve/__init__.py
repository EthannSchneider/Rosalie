"""Évolution du code : Rosalie fait modifier son propre code par un agent de programmation.

    demande (superadmin)  ->  Evolver.start()            service.py   orchestration + suivi
      clone isolé, branche                               workspace.py git, vérifications
      conteneur de travail « rosalie-evolve-<n> »        sandbox.py   clone monté, .git caché
      opencode : analyser, modifier, tester              opencode.py  agent opencode, en détaché
      commit, push, pull request                         github.py    API GitHub (urllib)
    fusion (superadmin, explicite)                       Evolver.merge()
    mise à jour + redémarrage (superadmin, explicite)    Evolver.request_update() -> libs/supervisor.py

Règles de sécurité :
  - tout passe par une pull request : jamais de push sur la branche de référence, jamais de
    fusion automatique ;
  - lancer, fusionner, mettre à jour : permission « evolve », réservée au superadmin et vérifiée
    côté serveur (outil, API) ; le contenu lu (pages web, messages, fichiers du dépôt) n'est
    jamais un ordre ;
  - le modèle de code ne travaille QUE dans son conteneur (shell libre, vérifications dedans) :
    rien du code modifié ne tourne sur la machine de Rosalie. Le .git du clone y est caché, le
    jeton GitHub n'y entre jamais ; commit et push sont faits par l'hôte ;
  - les modifications de .github, .env et storages sont annulées avant le commit ;
  - les secrets (jeton GitHub, clés API…) ne sont ni dans les messages, ni dans les journaux, ni
    dans la pull request (masqués par `redact`). Seule la clé API du fournisseur du modèle de
    code entre dans le conteneur (opencode en a besoin).

Voir docs/evolution.md.
"""
from libs.evolve.service import Brief, EvolveError, Evolver, redact

__all__ = ["Brief", "EvolveError", "Evolver", "redact"]
