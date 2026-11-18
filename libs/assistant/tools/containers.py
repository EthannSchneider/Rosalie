"""Conteneurs Docker : son bac à sable. Elle y lance ce qu'elle veut (commandes, scripts,
serveurs, bases de données…) sans toucher à la machine : pas de dossier de l'hôte, nom toujours
préfixé « rosalie- », ressources limitées (libs/containers). Permission « act.containers »,
réglage `containers`."""
from libs.assistant.tools.base import ToolContext, ToolError, result_budget, tool
from libs.containers import (KEEP_ALIVE, ContainerError, Docker, Limits, Spec, full_name, parse_env,
                             parse_ports, truncate)

CONTAINER_TOOLS = frozenset({"container_run", "container_exec", "container_logs", "container_list",
                             "container_remove"})
RESERVED = ("rosalie-evolve-",)      # conteneurs de l'évolution du code (libs/evolve/sandbox.py)
KIND = "sandbox"


async def _docker(ctx: ToolContext) -> Docker:
    docker = getattr(ctx.rosalie, "docker", None)
    if docker is None or not getattr(ctx.config, "containers", False):
        raise ToolError("les conteneurs sont désactivés (Réglages → Conteneurs)")
    problem = await docker.problem()
    if problem:
        raise ToolError(problem)
    return docker


def _name(name: str) -> str:
    name = full_name(name)
    if name.startswith(RESERVED):
        raise ContainerError(f"le nom {name} est réservé à l'évolution du code : choisis-en un autre")
    return name


def _guard(func):
    async def wrapper(ctx: ToolContext, **arguments) -> str:
        try:
            return await func(ctx, **arguments)
        except ContainerError as error:
            raise ToolError(str(error)) from None
    wrapper.__name__ = func.__name__
    return wrapper


@tool("container_run",
      "Crée et démarre un conteneur Docker à toi (ton bac à sable : tu peux y installer et y lancer "
      "ce que tu veux, sans risque pour la machine). Son nom est toujours préfixé « rosalie- ». "
      "Ensuite, lance des commandes dedans avec container_exec.",
      {"name": ("string", "Nom court du conteneur (ex : tests, site, base)"),
       "image": ("string", "Image Docker (ex : python:3.13-slim, node:22, postgres:17). Vide = image par défaut"),
       "command": ("string", "Vide = le conteneur attend tes commandes (container_exec). « image » = "
                             "lance le service prévu par l'image (nginx, postgres…). Sinon : la "
                             "commande à lancer au démarrage"),
       "ports": ("string", "Ports à publier sur cette machine, « hôte:conteneur » (ex : 8080:80)"),
       "env": ("string", "Variables d'environnement, « CLE=valeur » séparées par des virgules")},
      required=("name",))
@_guard
async def container_run(ctx: ToolContext, name: str, image: str = "", command: str = "",
                        ports: str = "", env: str = "") -> str:
    docker = await _docker(ctx)
    config = ctx.config
    name = _name(name)
    existing = await docker.list(KIND)
    if len(existing) >= config.containers_max:
        raise ToolError(f"déjà {len(existing)} conteneurs ({', '.join(c['name'] for c in existing)}) : "
                        f"le maximum est {config.containers_max}. Supprimes-en un (container_remove)")
    command = command.strip()
    if not command:
        argv = KEEP_ALIVE
    elif command.lower() == "image":
        argv = None
    else:
        argv = ["sh", "-c", command]
    image = image.strip() or config.containers_image
    await docker.run(Spec(name, image, argv, env=parse_env(env), ports=parse_ports(ports),
                          network=config.containers_network, limits=Limits.of(config), kind=KIND))
    published = ", ".join(f"http://127.0.0.1:{host} -> port {inside}" for host, inside in parse_ports(ports))
    return (f"Conteneur {name} démarré (image {image})."
            + (f" Ports : {published}." if published else "")
            + ("" if config.containers_network else " Il n'a pas d'accès réseau (réglage).")
            + " Lance des commandes avec container_exec ; supprime-le quand tu n'en as plus besoin.")


@tool("container_exec",
      "Lance une commande shell dans un de tes conteneurs et renvoie sa sortie (installer un "
      "paquet, écrire un fichier, lancer un script ou des tests…). Chaque appel est une nouvelle "
      "commande : enchaîne avec « && » ou « cd dossier && … ».",
      {"name": ("string", "Nom du conteneur"),
       "command": ("string", "Commande shell (sh -c)"),
       "timeout": ("integer", "Durée max en secondes (défaut et maximum : le réglage)")},
      required=("name", "command"))
@_guard
async def container_exec(ctx: ToolContext, name: str, command: str, timeout: int = 0) -> str:
    docker = await _docker(ctx)
    limit = ctx.config.containers_timeout
    try:
        seconds = min(limit, int(timeout)) if int(timeout) > 0 else limit
    except (TypeError, ValueError):
        seconds = limit
    result = await docker.exec(_name(name), command, timeout=seconds)
    output = truncate(result.output, min(result_budget(ctx), 12_000))
    return f"{result.summary()}\n{output or '(aucune sortie)'}"


@tool("container_logs", "Dernières lignes des journaux d'un de tes conteneurs (sortie de sa commande "
      "de démarrage : utile pour un service, ou un conteneur qui s'est arrêté).",
      {"name": ("string", "Nom du conteneur"), "lines": ("integer", "Nombre de lignes (défaut 80)")},
      required=("name",))
@_guard
async def container_logs(ctx: ToolContext, name: str, lines: int = 80) -> str:
    docker = await _docker(ctx)
    output = await docker.logs(_name(name), lines)
    return truncate(output, min(result_budget(ctx), 12_000)) or "(aucun journal)"


@tool("container_list", "Liste tes conteneurs Docker (nom, image, état, ports).")
@_guard
async def container_list(ctx: ToolContext) -> str:
    docker = await _docker(ctx)
    rows = await docker.list()
    if not rows:
        return "Aucun conteneur à toi pour l'instant."
    return "\n".join(f"{row['name']} — {row['image']} — {row['status']}"
                     + (f" — {row['ports']}" if row["ports"] else "") for row in rows)


@tool("container_remove", "Arrête et supprime un de tes conteneurs (tout ce qu'il contient est perdu).",
      {"name": ("string", "Nom du conteneur")}, required=("name",))
@_guard
async def container_remove(ctx: ToolContext, name: str) -> str:
    docker = await _docker(ctx)
    name = _name(name)
    if not await docker.remove(name):
        raise ToolError(f"le conteneur {name} n'existe pas")
    return f"Conteneur {name} supprimé."
