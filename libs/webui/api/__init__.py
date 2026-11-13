"""Versions de l'API. Une nouvelle version = un nouveau module (v2.py) avec sa table de routes,
servi à côté de l'ancienne tant que l'interface en dépend."""
from libs.webui.api import v1

VERSIONS = {"v1": v1}

__all__ = ["VERSIONS", "v1"]
