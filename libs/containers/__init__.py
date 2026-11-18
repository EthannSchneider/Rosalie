"""Conteneurs Docker de Rosalie (toujours préfixés « rosalie- ») : son bac à sable pour lancer
des commandes, des services, et le travail du modèle de code (libs/evolve/sandbox.py).

Voir docs/conteneurs.md.
"""
from libs.containers.docker import (KEEP_ALIVE, PREFIX, ContainerError, Docker, ExecResult, Limits, Spec,
                                    check_image, full_name, parse_env, parse_ports, truncate)

__all__ = ["KEEP_ALIVE", "PREFIX", "ContainerError", "Docker", "ExecResult", "Limits", "Spec",
           "check_image", "full_name", "parse_env", "parse_ports", "truncate"]
