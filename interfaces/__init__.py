"""Les interfaces de Rosalie : par où on lui parle. Le cœur (libs/core/) ne connaît que le
contrat `libs.core.interface.Interface` ; chaque interface vit dans son dossier.

Ajouter une interface :
  1. interfaces/<nom>/__init__.py avec une sous-classe d'Interface (voir libs/core/interface.py
     et interfaces/terminal/ comme exemple minimal) ;
  2. l'enregistrer ci-dessous ;
  3. l'activer : INTERFACES="discord,<nom>" dans le .env.
"""
import importlib

from libs.core.interface import Interface

AVAILABLE = {
    "discord": "interfaces.discord:DiscordInterface",
    "terminal": "interfaces.terminal:TerminalInterface",
}


def load(name: str, rosalie) -> Interface:
    """Instancie l'interface `name` (import paresseux : discord n'est chargé que si utilisé)."""
    target = AVAILABLE.get(name)
    if target is None:
        raise ValueError(f"interface inconnue « {name} » (disponibles : {', '.join(AVAILABLE)})")
    module, _, cls = target.partition(":")
    return getattr(importlib.import_module(module), cls)(rosalie)
