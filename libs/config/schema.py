"""Description de chaque réglage : type, valeur par défaut, groupe, aide.

C'est la source unique pour :
  - `Config` (libs/config/__init__.py) : valeurs par défaut et conversion ;
  - l'import automatique depuis l'ancien .env (`env=`) ;
  - la commande `python bot.py settings` ;
  - l'interface web (ses formulaires sont générés à partir de ce schéma).

Ajouter un réglage = un `Field` ici + l'attribut du même nom dans `Config` (+ docs).

Valeurs stockées (JSON) selon `kind` :
  bool, int, float, str, secret, model, hours, choice -> la valeur telle quelle
  ids                                                  -> liste de chaînes (IDs Discord : trop
                                                          grands pour les nombres JavaScript)
  list, tools                                          -> liste de chaînes
  persona                                              -> nom d'une personnalité
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class SettingError(ValueError):
    """Valeur refusée : le message est montré tel quel à l'utilisateur."""


@dataclass(frozen=True)
class Field:
    key: str                    # nom du réglage (= attribut de Config)
    kind: str                   # voir la docstring du module
    default: Any
    group: str
    label: str
    help: str = ""
    env: str = ""               # ancien nom dans le .env (importé une fois)
    choices: tuple[str, ...] = ()
    min: float | None = None
    max: float | None = None
    restart: bool = False       # pris en compte seulement au prochain démarrage

    def public(self) -> dict:
        """Description envoyée à l'interface web."""
        return {"key": self.key, "kind": self.kind, "default": self.default, "group": self.group,
                "label": self.label, "help": self.help, "env": self.env,
                "choices": list(self.choices), "min": self.min, "max": self.max,
                "restart": self.restart, "secret": self.kind == "secret"}


GROUPS = ("Discord", "Personnalité", "Ollama", "Conversation", "Outils", "Internet",
          "Exécution de code", "Rythme", "Heartbeat")

FIELDS: tuple[Field, ...] = (
    # --- Discord ----------------------------------------------------------------------------
    Field("discord_token", "secret", "", "Discord", "Token du bot",
          "Developer Portal > Bot. Active « Message Content Intent » et « Server Members Intent ».",
          env="ROSALIE_TOKEN", restart=True),
    Field("public_replies", "bool", True, "Discord", "Discuter avec les autres",
          "Les autres personnes peuvent lui parler (DM, mention, son nom) : réponses seulement, "
          "aucune action, aucun accès à ses souvenirs.", env="PUBLIC_REPLIES"),
    Field("public_cooldown", "int", 5, "Discord", "Délai anti-spam (s)",
          "Secondes minimum entre deux réponses à une même personne (non-owner).",
          env="PUBLIC_COOLDOWN", min=0, max=3600),
    Field("channel_ids", "ids", [], "Discord", "Salons dédiés",
          "Salons où elle répond à tous tes messages (aussi : /rosalie here).",
          env="ROSALIE_CHANNEL_IDS"),

    # --- Personnalité -----------------------------------------------------------------------
    Field("persona", "persona", "rosalie", "Personnalité", "Personnalité active",
          "Le prompt système de son personnage. « rosalie » est celle d'origine (non modifiable) ; "
          "crée les tiennes dans l'onglet Personas."),
    Field("names", "list", ["rosalie"], "Personnalité", "Noms qui l'appellent",
          "Mots qui la réveillent dans un message. Le premier est le nom qu'elle se donne.",
          env="ROSALIE_NAMES"),

    # --- Ollama -----------------------------------------------------------------------------
    Field("ollama_url", "str", "http://127.0.0.1:11434", "Ollama", "Adresse d'Ollama",
          env="OLLAMA_URL"),
    Field("ollama_model", "model", "qwen3:8b", "Ollama", "Modèle",
          "Après le fine-tune : rosalie. Aussi : /rosalie model.", env="OLLAMA_MODEL"),
    Field("decider_model", "model", "", "Ollama", "Modèle « dois-je répondre ? »",
          "Vide = le même modèle.", env="DECIDER_MODEL"),
    Field("embed_model", "model", "nomic-embed-text", "Ollama", "Modèle d'embeddings",
          "Mémoire à long terme. En changer rend les souvenirs déjà enregistrés difficiles à "
          "retrouver.", env="EMBED_MODEL", restart=True),
    Field("ollama_keep_alive", "str", "30m", "Ollama", "Garder le modèle chargé",
          "Durée pendant laquelle Ollama garde le modèle en mémoire (ex : 30m, 2h, -1).",
          env="OLLAMA_KEEP_ALIVE"),
    Field("num_ctx", "int", 16384, "Ollama", "Contexte (tokens)",
          "Sa mémoire de travail. Trop petit => réponses coupées ou question perdue.",
          env="OLLAMA_NUM_CTX", min=2048, max=1_048_576),
    Field("temperature", "float", 0.6, "Ollama", "Température",
          "Plus haut = plus créative, plus bas = plus sage.", env="OLLAMA_TEMPERATURE",
          min=0, max=2),

    # --- Conversation -----------------------------------------------------------------------
    Field("history_size", "int", 30, "Conversation", "Historique par salon",
          "Messages gardés par conversation (mémoire courte).", env="HISTORY_SIZE",
          min=2, max=500, restart=True),
    Field("conversation_timeout", "int", 180, "Conversation", "Suivi de conversation (s)",
          "Secondes pendant lesquelles elle te suit sans être nommée.",
          env="CONVERSATION_TIMEOUT", min=0, max=86400),
    Field("use_llm_decider", "bool", True, "Conversation", "Décider avec le modèle",
          "Un petit appel au modèle tranche les cas ambigus (« me parle-t-on ? »).",
          env="USE_LLM_DECIDER"),
    Field("ignore_prefixes", "list", ["//"], "Conversation", "Préfixes ignorés",
          "Tes messages commençant par ces préfixes sont ignorés.", env="IGNORE_PREFIXES"),
    Field("max_tool_steps", "int", 50, "Conversation", "Actions enchaînées max",
          "Nombre max d'actions par message (0 = illimité).", env="MAX_TOOL_STEPS",
          min=0, max=1000),
    Field("progress_every", "int", 6, "Conversation", "Point d'étape toutes les",
          "Toutes les N actions, elle t'envoie un résumé de ce qu'elle fait (0 = jamais).",
          env="PROGRESS_EVERY", min=0, max=1000),

    # --- Outils -----------------------------------------------------------------------------
    Field("disabled_tools", "tools", [], "Outils", "Outils désactivés",
          "Chaque outil coûte ~100 tokens de contexte : moins d'outils = prompt plus court.",
          env="DISABLED_TOOLS"),

    # --- Internet ---------------------------------------------------------------------------
    Field("web_access", "bool", True, "Internet", "Accès internet",
          "Outils de recherche, lecture de pages, images et météo.", env="WEB_ACCESS"),
    Field("web_search_provider", "choice", "duckduckgo", "Internet", "Moteur de recherche",
          "duckduckgo (sans clé), searxng (auto-hébergé) ou brave (clé API).",
          env="WEB_SEARCH_PROVIDER", choices=("duckduckgo", "searxng", "brave")),
    Field("searxng_url", "str", "", "Internet", "Adresse SearXNG",
          "Ex : http://127.0.0.1:8080 si tu héberges SearXNG.", env="SEARXNG_URL"),
    Field("brave_api_key", "secret", "", "Internet", "Clé API Brave",
          "https://brave.com/search/api (offre gratuite).", env="BRAVE_API_KEY"),
    Field("web_contact", "str", "", "Internet", "Contact pour Wikimedia",
          "Images Wikimedia Commons : leur règle exige un contact (e-mail ou URL) dans le "
          "User-Agent. Vide = Wikimedia n'est pas utilisé.", env="WEB_CONTACT"),
    Field("web_browser", "choice", "auto", "Internet", "Navigateur virtuel",
          "Pour les sites en JavaScript : auto (si la page est vide), always ou never.",
          env="WEB_BROWSER", choices=("auto", "always", "never")),

    # --- Exécution de code ------------------------------------------------------------------
    Field("code_exec", "bool", True, "Exécution de code", "Exécution de code",
          "Elle écrit un bloc run-python / run-bash, qui ne tourne qu'après ta confirmation. "
          "Dossier de travail : storages/workspace.", env="CODE_EXEC"),
    Field("code_timeout", "int", 60, "Exécution de code", "Durée max (s)",
          "Secondes max par exécution.", env="CODE_TIMEOUT", min=1, max=3600),
    Field("code_max_runs", "int", 3, "Exécution de code", "Exécutions enchaînées max",
          "Ex : quand elle corrige une erreur.", env="CODE_MAX_RUNS", min=0, max=20),

    # --- Rythme -----------------------------------------------------------------------------
    Field("reply_delay", "float", 2.0, "Rythme", "Calme avant de répondre (s)",
          "Elle attend que tu aies fini d'écrire (plusieurs messages, « écrit… »).",
          env="REPLY_DELAY", min=0, max=60),
    Field("reply_max_wait", "float", 20.0, "Rythme", "Attente max (s)",
          "Au-delà, elle répond quand même.", env="REPLY_MAX_WAIT", min=0, max=600),

    # --- Heartbeat --------------------------------------------------------------------------
    Field("heartbeat", "bool", True, "Heartbeat", "Heartbeat",
          "Battement régulier : relances programmées (plan_followup) et moments de réflexion.",
          env="HEARTBEAT"),
    Field("heartbeat_interval", "int", 60, "Heartbeat", "Intervalle (s)",
          "Secondes entre deux battements.", env="HEARTBEAT_INTERVAL", min=10, max=3600),
    Field("initiative", "bool", True, "Heartbeat", "Initiative",
          "Elle peut t'écrire d'elle-même (aussi : /rosalie initiative).", env="INITIATIVE"),
    Field("initiative_every", "int", 45, "Heartbeat", "Réflexion toutes les (min)",
          "Minutes entre deux moments de réflexion.", env="INITIATIVE_EVERY", min=1, max=10080),
    Field("initiative_min_silence", "int", 60, "Heartbeat", "Silence avant initiative (min)",
          "Minutes sans message avant qu'elle prenne l'initiative.",
          env="INITIATIVE_MIN_SILENCE", min=0, max=10080),
    Field("initiative_max_per_day", "int", 3, "Heartbeat", "Messages spontanés max / 24 h",
          env="INITIATIVE_MAX_PER_DAY", min=0, max=100),
    Field("quiet_hours", "hours", "23-8", "Heartbeat", "Heures calmes",
          "Jamais d'initiative pendant ces heures, ex : 23-8 (vide = aucune).",
          env="QUIET_HOURS"),
)

BY_KEY: dict[str, Field] = {field.key: field for field in FIELDS}
BY_ENV: dict[str, Field] = {field.env: field for field in FIELDS if field.env}

PERSONA_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_TRUE = ("1", "true", "yes", "oui", "on", "o", "y")
_FALSE = ("0", "false", "no", "non", "off", "n")


def find(name: str) -> Field:
    """Un réglage par son nom (ollama_model) ou son ancien nom .env (OLLAMA_MODEL)."""
    field = BY_KEY.get(name.strip().lower()) or BY_ENV.get(name.strip().upper())
    if field is None:
        raise SettingError(f"réglage inconnu « {name} »")
    return field


def parse(field: Field, text: str) -> Any:
    """Texte (ligne de commande, .env) -> valeur normalisée."""
    text = text.strip()
    if field.kind == "bool":
        if text.lower() in _TRUE:
            return True
        if text.lower() in _FALSE:
            return False
        raise SettingError(f"{field.key} : « {text} » n'est pas oui/non")
    if field.kind in ("ids", "list", "tools"):
        separators = r"[,\s]+" if field.kind in ("ids", "tools") else r","
        return normalize(field, [part for part in re.split(separators, text) if part.strip()])
    return normalize(field, text)


def normalize(field: Field, value: Any) -> Any:
    """Valeur venant du JSON (interface web) ou de `parse` -> valeur validée à stocker.
    Les outils et les personnalités sont vérifiés par le magasin (ils en dépendent)."""
    kind = field.kind
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return parse(field, value)
        raise SettingError(f"{field.key} : oui ou non attendu")
    if kind in ("int", "float"):
        try:
            number = float(value) if kind == "float" else _to_int(value)
        except (TypeError, ValueError):
            raise SettingError(f"{field.key} : nombre attendu") from None
        if field.min is not None and number < field.min:
            raise SettingError(f"{field.key} : minimum {_fmt(field.min)}")
        if field.max is not None and number > field.max:
            raise SettingError(f"{field.key} : maximum {_fmt(field.max)}")
        return number
    if kind in ("ids", "list", "tools"):
        items = value.split(",") if isinstance(value, str) else value
        if not isinstance(items, (list, tuple)):
            raise SettingError(f"{field.key} : liste attendue")
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if kind == "ids":
            bad = [item for item in cleaned if not item.isdigit()]
            if bad:
                raise SettingError(f"{field.key} : « {bad[0]} » n'est pas un identifiant numérique")
            return sorted(set(cleaned), key=int)
        return list(dict.fromkeys(cleaned))
    if not isinstance(value, str):
        raise SettingError(f"{field.key} : texte attendu")
    value = value.strip()
    if kind == "choice":
        value = value.lower()
        if value not in field.choices:
            raise SettingError(f"{field.key} : choisir parmi {', '.join(field.choices)}")
    elif kind == "hours":
        if value and not re.fullmatch(r"([01]?\d|2[0-3])-([01]?\d|2[0-3])", value):
            raise SettingError(f"{field.key} : format attendu « 23-8 » (ou vide)")
    elif kind == "persona":
        value = value.lower()
        if not PERSONA_NAME.match(value):
            raise SettingError(f"{field.key} : nom de personnalité invalide")
    elif kind == "str" and field.key.endswith("_url") and value:
        if not re.match(r"^https?://", value):
            raise SettingError(f"{field.key} : adresse http(s):// attendue")
        value = value.rstrip("/")
    return value


def display(field: Field, value: Any) -> str:
    """Valeur lisible (ligne de commande). Les secrets ne sont jamais montrés."""
    if field.kind == "secret":
        return "(défini)" if value else "(vide)"
    if field.kind == "bool":
        return "oui" if value else "non"
    if isinstance(value, list):
        return ", ".join(value) if value else "(aucun)"
    if value == "":
        return "(vide)"
    return _fmt(value) if isinstance(value, float) else str(value)


def tool_catalog() -> list[dict]:
    """Tous les outils connus (génériques + Discord), pour choisir lesquels désactiver."""
    from libs.assistant.tools import GUEST_TOOLS, TOOLS, WEB_TOOLS
    try:
        import interfaces.discord.tools  # noqa: F401  (enregistre les outils Discord)
    except Exception:   # py-cord absent : seuls les outils génériques sont listés
        pass
    return [{"name": t.name, "description": t.description, "requires": t.requires,
             "confirm": bool(t.confirm), "guest": t.name in GUEST_TOOLS, "web": t.name in WEB_TOOLS}
            for t in TOOLS.values()]


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not number.is_integer():
        raise ValueError
    return int(number)


def _fmt(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)
