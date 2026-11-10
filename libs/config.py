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
    # Les seules personnes à qui Gideon obéit
    owner_ids: frozenset[int]
    channel_ids: frozenset[int]        # salons où Gideon répond à tout
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

    # Fichiers
    persona_file: Path
    storage_dir: Path

    @classmethod
    def from_env(cls) -> "Config":
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        return cls(
            owner_ids=_ids("OWNER_IDS"),
            channel_ids=_ids("GIDEON_CHANNEL_IDS"),
            names=_list("GIDEON_NAMES", "gideon"),
            ignore_prefixes=_list("IGNORE_PREFIXES", "//"),
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=model,
            decider_model=os.getenv("DECIDER_MODEL") or model,
            embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
            ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.6")),
            history_size=int(os.getenv("HISTORY_SIZE", "30")),
            conversation_timeout=int(os.getenv("CONVERSATION_TIMEOUT", "180")),
            use_llm_decider=_bool("USE_LLM_DECIDER", True),
            max_tool_steps=int(os.getenv("MAX_TOOL_STEPS", "6")),
            persona_file=_path("PERSONA_FILE", "personas/gideon.md"),
            storage_dir=_path("STORAGE_DIR", "storages"),
        )
