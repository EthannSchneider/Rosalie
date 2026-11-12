import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def _ids(name: str) -> frozenset[int]:
    raw = os.getenv(name, "")
    return frozenset(int(part) for part in raw.replace(" ", "").split(",") if part)


def _list(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "oui", "on")


def _path(name: str, default: str) -> Path:
    path = Path(os.getenv(name) or default)
    return path if path.is_absolute() else ROOT_DIR / path


@dataclass(frozen=True)
class Config:
    # Les seules personnes à qui Rosalie obéit
    owner_ids: frozenset[int]
    channel_ids: frozenset[int]        # salons où Rosalie répond à tout
    names: tuple[str, ...]             # noms qui la « réveillent » dans un message
    ignore_prefixes: tuple[str, ...]   # messages à ignorer

    # Ollama
    ollama_url: str
    ollama_model: str
    decider_model: str
    embed_model: str
    ollama_keep_alive: str
    num_ctx: int
    temperature: float

    # Conversation
    history_size: int
    conversation_timeout: int
    use_llm_decider: bool
    max_tool_steps: int

    # Internet
    web_access: bool
    web_search_provider: str           # duckduckgo | searxng | brave
    searxng_url: str
    brave_api_key: str
    web_browser: str                   # auto | always | never (navigateur virtuel pour le JavaScript)

    # Fichiers
    persona_file: Path
    storage_dir: Path

    # Les autres personnes : simple discussion (aucun outil Discord, aucun souvenir)
    public_replies: bool = True
    public_cooldown: int = 5           # secondes minimum entre deux réponses à une même personne

    # Rythme : attendre que tu aies fini d'écrire avant de répondre
    reply_delay: float = 2.0           # secondes de calme après ton dernier message / « écrit… »
    reply_max_wait: float = 20.0       # attente maximale avant de répondre quand même

    # Contact mis dans le User-Agent pour les sites qui l'exigent (Wikimedia Commons). Vide = pas utilisé.
    web_contact: str = ""

    # Outils à ne pas proposer au modèle (chaque outil prend ~100 tokens de contexte)
    disabled_tools: tuple[str, ...] = ()

    # Exécution de code (toujours après confirmation de l'owner sur Discord)
    code_exec: bool = True
    code_timeout: int = 60             # secondes max par exécution
    code_max_runs: int = 3             # exécutions max enchaînées pour une même demande

    # Heartbeat : relances programmées et initiative (écrire d'elle-même)
    heartbeat: bool = True
    heartbeat_interval: int = 60       # secondes entre deux battements
    initiative: bool = True            # valeur par défaut (modifiable avec /rosalie initiative)
    initiative_every: int = 45         # minutes entre deux moments de réflexion
    initiative_min_silence: int = 60   # minutes de calme dans la conversation avant d'écrire d'elle-même
    initiative_max_per_day: int = 3
    quiet_hours: str = "23-8"          # jamais d'initiative pendant ces heures (vide = aucune)

    @classmethod
    def from_env(cls) -> "Config":
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        return cls(
            owner_ids=_ids("OWNER_IDS"),
            channel_ids=_ids("ROSALIE_CHANNEL_IDS"),
            names=_list("ROSALIE_NAMES", "rosalie"),
            ignore_prefixes=_list("IGNORE_PREFIXES", "//"),
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=model,
            decider_model=os.getenv("DECIDER_MODEL") or model,
            embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
            ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "16384")),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.6")),
            history_size=int(os.getenv("HISTORY_SIZE", "30")),
            conversation_timeout=int(os.getenv("CONVERSATION_TIMEOUT", "180")),
            use_llm_decider=_bool("USE_LLM_DECIDER", True),
            max_tool_steps=int(os.getenv("MAX_TOOL_STEPS", "6")),
            web_access=_bool("WEB_ACCESS", True),
            web_search_provider=os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo").lower(),
            searxng_url=os.getenv("SEARXNG_URL", ""),
            brave_api_key=os.getenv("BRAVE_API_KEY", ""),
            web_browser=os.getenv("WEB_BROWSER", "auto").lower(),
            persona_file=_path("PERSONA_FILE", "personas/rosalie.md"),
            storage_dir=_path("STORAGE_DIR", "storages"),
            public_replies=_bool("PUBLIC_REPLIES", True),
            public_cooldown=int(os.getenv("PUBLIC_COOLDOWN", "5")),
            reply_delay=float(os.getenv("REPLY_DELAY", "2")),
            reply_max_wait=float(os.getenv("REPLY_MAX_WAIT", "20")),
            web_contact=os.getenv("WEB_CONTACT", "").strip(),
            disabled_tools=_list("DISABLED_TOOLS", ""),
            code_exec=_bool("CODE_EXEC", True),
            code_timeout=int(os.getenv("CODE_TIMEOUT", "60")),
            code_max_runs=int(os.getenv("CODE_MAX_RUNS", "3")),
            heartbeat=_bool("HEARTBEAT", True),
            heartbeat_interval=int(os.getenv("HEARTBEAT_INTERVAL", "60")),
            initiative=_bool("INITIATIVE", True),
            initiative_every=int(os.getenv("INITIATIVE_EVERY", "45")),
            initiative_min_silence=int(os.getenv("INITIATIVE_MIN_SILENCE", "60")),
            initiative_max_per_day=int(os.getenv("INITIATIVE_MAX_PER_DAY", "3")),
            quiet_hours=os.getenv("QUIET_HOURS", "23-8"),
        )
