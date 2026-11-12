"""Socle des outils : contexte, registre, décorateur @tool, exécution sécurisée, helpers.

Indépendant de toute messagerie. Un outil propre à une interface se déclare avec
@tool(..., requires="discord") : il n'est proposé au modèle que si cette interface tourne
(et reste utilisable depuis une autre interface, ex : envoyer sur Discord depuis le terminal).
"""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from libs.core.types import Conversation, Person
from libs.log import Log

if TYPE_CHECKING:
    from libs.core.rosalie import Rosalie


class ToolError(Exception):
    """Erreur attendue d'un outil : son message est renvoyé tel quel au modèle."""


@dataclass
class ToolContext:
    rosalie: Rosalie
    conversation: Conversation   # où l'ordre a été donné
    person: Person               # qui l'a donné

    @property
    def is_owner(self) -> bool:
        return self.person.is_owner

    @property
    def config(self):
        return self.rosalie.config

    def interface(self, name: str | None = None):
        """L'interface demandée (par défaut celle de la conversation)."""
        name = name or self.conversation.interface
        interface = self.rosalie.interfaces.get(name)
        if interface is None:
            raise ToolError(f"l'interface {name} n'est pas lancée")
        return interface


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, tuple[str, str]]          # nom -> (type JSON, description)
    required: tuple[str, ...]
    func: Callable[..., Awaitable[str]]
    confirm: str | None = None                  # texte de confirmation => outil dangereux
    requires: str | None = None                 # interface nécessaire (« discord »…)

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {name: {"type": kind, "description": desc}
                               for name, (kind, desc) in self.params.items()},
                "required": list(self.required),
            },
        }}


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, params: dict | None = None,
         required: tuple[str, ...] = (), confirm: str | None = None, requires: str | None = None):
    def decorator(func):
        TOOLS[name] = Tool(name, description, params or {}, required, func, confirm, requires)
        return func
    return decorator


WEB_TOOLS = {"web_search", "fetch_url", "send_image", "send_image_url", "weather"}
# Seuls outils permis quand ce n'est pas un owner qui parle : chercher une info, rien d'autre
GUEST_TOOLS = {"web_search", "fetch_url", "weather"}


def schemas(web_access: bool = True, guest: bool = False,
            disabled: tuple[str, ...] | frozenset[str] = (),
            interfaces: set[str] | frozenset[str] | None = None) -> list[dict]:
    """interfaces : interfaces lancées (None = toutes, pour les tests)."""
    return [t.schema() for t in TOOLS.values()
            if (web_access or t.name not in WEB_TOOLS) and (not guest or t.name in GUEST_TOOLS)
            and t.name not in disabled
            and (t.requires is None or interfaces is None or t.requires in interfaces)]


async def execute(ctx: ToolContext, name: str, arguments: dict | str | None) -> str:
    """Exécute un appel d'outil et renvoie un texte pour le LLM (jamais d'exception)."""
    selected = TOOLS.get(name)
    if selected is None:
        return f"Erreur : l'outil « {name} » n'existe pas."
    config = ctx.config
    if name in getattr(config, "disabled_tools", ()):
        return f"Erreur : l'outil « {name} » est désactivé (DISABLED_TOOLS)."
    if name not in GUEST_TOOLS and not ctx.is_owner:
        Log.warning(f"Tool {name} refused for non-owner {ctx.person.key}")
        return "Erreur : seul mon créateur peut me demander ça."
    if name in WEB_TOOLS and not getattr(config, "web_access", True):
        return "Erreur : l'accès internet est désactivé (WEB_ACCESS=false)."
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return "Erreur : arguments JSON invalides."
    arguments = {k: v for k, v in (arguments or {}).items()
                 if k in selected.params and v not in (None, "")}
    missing = [r for r in selected.required if r not in arguments]
    if missing:
        return f"Erreur : paramètre(s) manquant(s) : {', '.join(missing)}."

    try:
        if selected.requires:
            ctx.interface(selected.requires)   # lancée ?
        if selected.confirm:
            text = selected.confirm.format_map(_Default(arguments))
            confirmed, _ = await ctx.interface().confirm(ctx.conversation, text)
            if not confirmed:
                return "Action annulée : l'utilisateur n'a pas confirmé."
        result = await selected.func(ctx, **arguments)
    except ToolError as error:
        result = f"Erreur : {error}"
    except (TypeError, ValueError) as error:
        result = f"Erreur : arguments invalides ({error})."
    except Exception as error:   # erreur propre à une messagerie (permission…) ou imprévue
        result = _describe(ctx, error)
    Log.command(f"tool {name}({arguments}) -> {result[:200]}")
    return result


def _describe(ctx: ToolContext, error: Exception) -> str:
    for interface in ctx.rosalie.interfaces.values():
        described = interface.describe_error(error)
        if described:
            return described
    Log.error(f"Outil en échec : {error}\n{traceback.format_exc()}")
    return f"Erreur : {type(error).__name__} : {error}"


class _Default(dict):
    def __missing__(self, key):
        return "?"


def result_budget(ctx: "ToolContext", share: float = 0.4) -> int:
    """Taille (en caractères) qu'un résultat d'outil peut occuper sans saturer le contexte du
    modèle. Les outils qui lisent beaucoup s'arrêtent là et proposent de continuer."""
    num_ctx = getattr(ctx.config, "num_ctx", None) or 16384
    return int(num_ctx * 3.2 * share)


def _int(value, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default
