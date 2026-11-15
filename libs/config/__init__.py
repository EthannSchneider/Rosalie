"""Configuration de Rosalie.

Deux sources :
  - le .env : seulement le démarrage (où sont les données, adresse et port du site web) ;
  - storages/config.sqlite3 (`ConfigStore`) : tous les autres réglages et les personnalités,
    modifiables à chaud avec `python bot.py settings` ou l'interface web.

Au premier lancement, les anciens réglages du .env (et de settings.json) sont importés dans la
base ; ensuite le .env n'est plus lu pour eux. Le schéma (types, défauts, aide) est dans schema.py.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from libs.config.schema import BY_ENV, BY_KEY, FIELDS, PROVIDERS, SettingError, parse, split_model
from libs.config.store import DEFAULT_PERSONA, ConfigStore

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STORE_FILE = "config.sqlite3"
# Remplacées : personnalités, comptes, et INTERFACES (python bot.py lance tout sauf le terminal)
OBSOLETE_ENV = ("PERSONA_FILE", "WEB_UI", "WEB_UI_PASSWORD", "OWNER_IDS", "INTERFACES")
LEGACY_OWNERS = "legacy_owner_ids"   # anciens OWNER_IDS, valables tant qu'aucun compte n'est lié
ENV_IMPORTED = "env_imported"


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "oui", "on")


def _path(name: str, default: str) -> Path:
    path = Path(os.getenv(name) or default)
    return path if path.is_absolute() else ROOT_DIR / path


def storage_dir() -> Path:
    return _path("STORAGE_DIR", "storages")


@dataclass(frozen=True)
class Config:
    """Photo des réglages à un instant donné (Rosalie.config la renouvelle quand ils changent)."""
    # Discord
    discord_token: str                 # (à qui elle obéit : comptes du site liés à Discord)
    public_replies: bool               # les autres : simple discussion (aucune action, aucun souvenir)
    guest_web: bool                    # les inconnus (sans compte) peuvent faire faire des recherches web
    public_cooldown: int               # secondes minimum entre deux réponses à une même personne
    channel_ids: frozenset[int]        # salons Discord où Rosalie répond à tout

    # Personnalité
    persona: str                       # nom de la personnalité active (libs/llm/persona.py)
    names: tuple[str, ...]             # noms qui la « réveillent » dans un message

    # Providers : lesquels sont activés, et comment les joindre
    providers: tuple[str, ...]
    ollama_url: str
    ollama_allowed_models: tuple[str, ...]   # vide = tous
    ollama_keep_alive: str
    openai_api_key: str
    anthropic_api_key: str
    gemini_api_key: str

    # Modèles : toujours « fournisseur:nom » (libs.config.schema.split_model)
    chat_model: str
    decider_model: str                 # vide dans les réglages = modèle principal (résolu ici)
    embed_model: str
    code_model: str                    # vide dans les réglages = modèle principal (résolu ici)
    code_num_ctx: int
    num_ctx: int
    temperature: float

    # Conversation
    history_size: int
    conversation_timeout: int
    use_llm_decider: bool
    ignore_prefixes: tuple[str, ...]   # messages à ignorer
    max_tool_steps: int
    progress_every: int

    # Outils à ne pas proposer au modèle (chaque outil prend ~100 tokens de contexte)
    disabled_tools: tuple[str, ...]

    # Internet
    web_access: bool
    web_search_provider: str           # duckduckgo | searxng | brave
    searxng_url: str
    brave_api_key: str
    web_contact: str                   # contact User-Agent (Wikimedia Commons). Vide = pas utilisé.
    web_browser: str                   # auto | always | never (navigateur virtuel pour le JavaScript)

    # Exécution de code (toujours après confirmation de l'owner)
    code_exec: bool
    code_timeout: int
    code_max_runs: int

    # Évolution du code (libs/evolve)
    evolve: bool
    evolve_repo: str
    evolve_base_branch: str
    github_token: str
    evolve_max_steps: int
    evolve_check_timeout: int

    # Rythme : attendre que tu aies fini d'écrire avant de répondre
    reply_delay: float
    reply_max_wait: float

    # Heartbeat : relances programmées et initiative (écrire d'elle-même)
    heartbeat: bool
    heartbeat_interval: int
    initiative: bool
    initiative_every: int
    initiative_min_silence: int
    initiative_max_per_day: int
    quiet_hours: str

    # Démarrage (.env)
    storage_dir: Path

    def __repr__(self) -> str:   # jamais de secret dans un log
        return f"Config(model={self.chat_model!r}, persona={self.persona!r}, ...)"

    @property
    def secrets(self) -> tuple[str, ...]:
        """Toutes les valeurs secrètes définies (pour les masquer dans un texte qui sort)."""
        return tuple(str(getattr(self, field.key)) for field in FIELDS
                     if field.kind == "secret" and getattr(self, field.key))

    @property
    def api_keys(self) -> dict[str, str]:
        """Clé API de chaque fournisseur distant."""
        return {"openai": self.openai_api_key, "anthropic": self.anthropic_api_key,
                "gemini": self.gemini_api_key}

    @property
    def dedicated(self) -> frozenset[str]:
        """Salons dédiés des réglages, en clés « interface:id »."""
        return frozenset(f"discord:{channel_id}" for channel_id in self.channel_ids)

    @classmethod
    def from_values(cls, values: Mapping[str, Any], storage: Path | None = None) -> "Config":
        """Valeurs du schéma (JSON) -> Config typée. Les clés absentes prennent leur défaut."""
        converted = {}
        for field in FIELDS:
            value = values.get(field.key, field.default)
            if field.kind == "ids":
                value = frozenset(int(item) for item in value)
            elif field.kind in ("list", "tools", "choices"):
                value = tuple(value)
            elif field.kind == "model" and value:   # anciennes valeurs sans préfixe : Ollama
                value = ":".join(split_model(value))
            elif field.kind == "float":
                value = float(value)
            converted[field.key] = value
        converted["decider_model"] = converted["decider_model"] or converted["chat_model"]
        converted["code_model"] = converted["code_model"] or converted["chat_model"]
        converted["names"] = tuple(name.lower() for name in converted["names"]) or ("rosalie",)
        return cls(**converted, storage_dir=storage or storage_dir())

    @classmethod
    def load(cls, store: ConfigStore, storage: Path | None = None) -> "Config":
        return cls.from_values(store.values(), storage)

    @classmethod
    def from_env(cls) -> "Config":
        """Réglages lus dans les variables d'environnement (tests, ancien fonctionnement)."""
        values, _ = env_values(os.environ)
        return cls.from_values(values)


def env_values(environ: Mapping[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Anciens réglages du .env -> (valeurs valides, erreurs)."""
    values: dict[str, Any] = {}
    errors: list[str] = []
    for name, field in BY_ENV.items():
        raw = environ.get(name)
        if raw is None or raw.strip() == "":
            continue
        try:
            values[field.key] = parse(field, raw)
        except SettingError as error:
            errors.append(f"{name} : {error}")
    return values, errors


def load_config(warn: bool = True) -> tuple[Config, ConfigStore]:
    """Ouvre storages/config.sqlite3 (en important l'ancien .env la première fois).
    warn : signaler les variables du .env qui ne sont plus lues."""
    from libs.log import Log
    storage = storage_dir()
    store = ConfigStore(storage / STORE_FILE)
    store.take_legacy("interfaces")              # réglage supprimé : python bot.py lance tout
    old_owners = store.take_legacy("owner_ids")   # réglage supprimé : remplacé par les comptes
    if old_owners:
        _remember_legacy_owners(store, old_owners)
    _migrate_models(store)
    if store.meta(ENV_IMPORTED) is None:
        imported = import_env(store, os.environ, storage)
        if imported:
            Log.info(f"Réglages importés du .env dans {storage / STORE_FILE} : {', '.join(imported)}")
    leftovers = sorted(name for name in BY_ENV if os.environ.get(name, "").strip())
    leftovers += [name for name in OBSOLETE_ENV if os.environ.get(name, "").strip()]
    if leftovers and warn:
        Log.warning("Ces variables du .env ne sont plus lues (les réglages sont dans "
                    f"{storage / STORE_FILE}, voir `python bot.py settings`) : {', '.join(leftovers)}")
    return Config.load(store, storage), store


def import_env(store: ConfigStore, environ: Mapping[str, str], storage: Path,
               force: bool = False) -> list[str]:
    """Copie les anciens réglages (.env, puis settings.json pour le modèle et l'initiative choisis
    sur Discord) dans la base. Une seule fois, sauf force=True. Retourne les clés importées."""
    from libs.log import Log
    first = store.meta(ENV_IMPORTED) is None
    if not first and not force:
        return []
    values, errors = env_values(environ)
    for error in errors:
        Log.warning(f"Import du .env : {error} (ignoré)")

    legacy = storage / "settings.json"
    if first and legacy.exists():   # choix faits sur Discord avant cette version
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if data.get("model"):
            values["chat_model"] = data["model"]
        if isinstance(data.get("initiative"), bool):
            values["initiative"] = data["initiative"]

    owners = [part for part in environ.get("OWNER_IDS", "").replace(",", " ").split() if part.isdigit()]
    if owners:
        _remember_legacy_owners(store, owners)

    persona = _import_persona_file(store, environ.get("PERSONA_FILE", ""))
    if persona:
        values["persona"] = persona

    applied = []
    for key, value in values.items():
        try:
            store.set(key, value)
            applied.append(key)
        except SettingError as error:
            Log.warning(f"Import du .env : {error} (ignoré)")
    store.set_meta(ENV_IMPORTED, "1")
    return applied


def _migrate_models(store: ConfigStore):
    """Anciens réglages (un seul fournisseur, un modèle par fournisseur) -> « fournisseur:nom »
    dans chat_model, et le fournisseur ajouté à ceux activés."""
    from libs.log import Log
    old_defaults = {"openai": "gpt-4o-mini", "anthropic": "claude-sonnet-4-5",
                    "gemini": "gemini-2.5-flash"}
    provider = store.take_legacy("llm_provider") or "ollama"
    models = {"ollama": store.take_legacy("ollama_model"),
              **{name: store.take_legacy(f"{name}_model") or default
                 for name, default in old_defaults.items()}}
    model = models.get(provider) if provider in PROVIDERS else None
    if not model or "chat_model" in store.overrides():
        return
    try:
        if provider not in store.get("providers"):
            store.set("providers", [*store.get("providers"), provider])
        store.set("chat_model", f"{provider}:{model}")
    except SettingError as error:
        Log.warning(f"Ancien modèle « {model} » non repris : {error}")


def _remember_legacy_owners(store: ConfigStore, ids):
    known = set(json.loads(store.meta(LEGACY_OWNERS) or "[]"))
    store.set_meta(LEGACY_OWNERS, json.dumps(sorted(known | {str(i) for i in ids}, key=int)))


def legacy_owner_ids(store: ConfigStore) -> frozenset[int]:
    return frozenset(int(i) for i in json.loads(store.meta(LEGACY_OWNERS) or "[]"))


def _import_persona_file(store: ConfigStore, raw: str) -> str | None:
    """PERSONA_FILE de l'ancien .env : une personnalité intégrée, ou un fichier à importer."""
    if not raw.strip():
        return None
    path = Path(raw.strip())
    path = path if path.is_absolute() else ROOT_DIR / path
    builtin = {p.resolve(): name for name, p in store.builtin_personas().items()}
    if path.resolve() in builtin:
        name = builtin[path.resolve()]
        return None if name == DEFAULT_PERSONA else name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in path.stem.lower())[:40] or "importee"
    if store.is_builtin(name):
        name = f"{name}-perso"
    if store.persona_text(name) is None and text.strip():
        store.save_persona(name, text)
    return name


@dataclass(frozen=True)
class WebUIOptions:
    """Où écoute le site (interface « web ») : .env WEB_UI_HOST, WEB_UI_PORT."""
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "WebUIOptions":
        return cls(host=os.getenv("WEB_UI_HOST", "127.0.0.1").strip() or "127.0.0.1",
                   port=int(os.getenv("WEB_UI_PORT", "8765") or 8765))


__all__ = ["BY_KEY", "Config", "ConfigStore", "ROOT_DIR", "SettingError", "WebUIOptions",
           "import_env", "load_config", "storage_dir"]
