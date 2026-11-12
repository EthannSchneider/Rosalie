import json
import re
from dataclasses import dataclass, field

from libs.assistant.code_runner import extract_code
from libs.assistant.tools import TOOLS, ToolContext, execute, schemas
from libs.llm.ollama import OllamaClient
from libs.log import Log


@dataclass
class AgentResult:
    text: str
    actions: list[str] = field(default_factory=list)
    # Appels d'outils + résultats (format Ollama), à garder dans l'historique de la conversation
    trace: list[dict] = field(default_factory=list)
    # Outils qui ont échoué : « nom : message » (toujours signalés à l'utilisateur)
    errors: list[str] = field(default_factory=list)


TRACE_RESULT_CHARS = 500   # résultats longs (pages web…) tronqués dans l'historique


_INLINE_CALL = re.compile(r"^\s*(\{.*\})\s*$", re.DOTALL)

# « Je vais vérifier… », « Laisse-moi regarder… » : le modèle annonce une action puis s'arrête
_ANNOUNCES_ACTION = re.compile(
    r"^\W*(je vais|je m'en occupe|laisse-moi|attends|je regarde|je vérifie|je cherche|"
    r"un instant|une seconde|je lis)\b", re.IGNORECASE)
NUDGE = ("(Note système : tu viens d'annoncer une action sans la faire. Fais-la maintenant "
         "avec les outils, puis donne ta réponse finale.)")

# « Je viens d'envoyer… », « C'est fait » alors qu'aucun outil n'a été appelé : mensonge à corriger
_CLAIMS_ACTION = re.compile(
    r"\b(je viens d['’](envoy|écri|transm|cré|suppr|donn|retir|not)|j['’]ai (bien )?(envoy|transmis|cré|supprim|donn|retir|expuls|banni|chang|not)|"
    r"c['’]est fait|message (privé )?(a été )?envoyé|c['’]est envoyé|envoyé à|"
    r"(salon|rôle|statut) (a été )?(créé|supprimé|donné|retiré|changé))", re.IGNORECASE)
CLAIM_NUDGE = ("(Note système : tu affirmes avoir fait une action, mais AUCUN outil n'a été appelé : "
               "rien n'a été fait. Si l'utilisateur demande une action, appelle maintenant l'outil "
               "correspondant (send_dm, send_message…). Sinon, réponds sans prétendre avoir agi.)")


CHARS_PER_TOKEN = 3.2      # estimation prudente (mesuré : ~3,4 en français avec les outils)
OUTPUT_RESERVE = 0.25      # part du contexte gardée pour la réponse
MIN_TOOL_RESULT = 600
CUT_NOTE = "\n… (coupé : trop long pour ma mémoire de travail)"
TRUNCATED_NOTE = ("\n\n⚠️ (Ma réponse a été coupée : ma mémoire de travail est pleine. "
                  "Augmente OLLAMA_NUM_CTX.)")


def _size(message: dict) -> int:
    size = len(message.get("content") or "")
    if message.get("tool_calls"):
        size += len(json.dumps(message["tool_calls"], ensure_ascii=False))
    return size


def fit_context(messages: list[dict], max_chars: int) -> bool:
    """Fait tenir la conversation dans le contexte du modèle, sinon Ollama coupe lui-même
    (et peut couper la question). 1) raccourcit les plus gros résultats d'outils,
    2) oublie le plus vieil historique. Ne touche jamais au prompt système ni au dernier
    message de l'utilisateur. Retourne True si quelque chose a été coupé."""
    cut = False
    while sum(map(_size, messages)) > max_chars:
        tools = [m for m in messages if m["role"] == "tool" and len(m["content"]) > MIN_TOOL_RESULT * 2]
        if not tools:
            break
        biggest = max(tools, key=lambda m: len(m["content"]))
        biggest["content"] = biggest["content"][:max(MIN_TOOL_RESULT, len(biggest["content"]) // 2)] + CUT_NOTE
        cut = True
    users = [i for i, m in enumerate(messages) if m["role"] == "user"]
    last_user = users[-1] if users else len(messages) - 1
    while sum(map(_size, messages)) > max_chars and last_user > 1:
        del messages[1]
        last_user -= 1
        # pas de résultat d'outil orphelin, et on recommence sur un message de l'utilisateur
        while last_user > 1 and messages[1]["role"] != "user":
            del messages[1]
            last_user -= 1
        cut = True
    return cut


def _inline_tool_calls(content: str) -> list[dict]:
    """Certains modèles écrivent l'appel en JSON dans le texte au lieu de tool_calls."""
    match = _INLINE_CALL.match(content or "")
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    name = data.get("name")
    if name not in TOOLS:
        return []
    arguments = data.get("parameters", data.get("arguments", {}))
    return [{"function": {"name": name, "arguments": arguments}}]


async def run_agent(llm: OllamaClient, messages: list[dict], ctx: ToolContext,
                    max_steps: int = 6, acted: bool = False) -> AgentResult:
    """Boucle « le modèle appelle des outils -> on lui renvoie les résultats »
    jusqu'à ce qu'il produise une réponse finale en texte.
    acted=True : une action a déjà eu lieu (code exécuté) -> pas de soupçon de mensonge."""
    actions: list[str] = []
    trace: list[dict] = []
    errors: list[str] = []
    tools = schemas(getattr(ctx.bot.config, "web_access", True), guest=not ctx.is_owner,
                    disabled=getattr(ctx.bot.config, "disabled_tools", ()))
    nudged = False
    num_ctx = getattr(ctx.bot.config, "num_ctx", 8192)
    budget = int(num_ctx * (1 - OUTPUT_RESERVE) * CHARS_PER_TOKEN) - len(json.dumps(tools, ensure_ascii=False))
    for _ in range(max_steps):
        if fit_context(messages, budget):
            Log.warning(f"Conversation raccourcie pour tenir dans le contexte (OLLAMA_NUM_CTX={num_ctx})")
        message = await llm.chat_message(messages, tools=tools)
        content = message.get("content", "") or ""
        if message.get("done_reason") == "length":
            Log.warning("Réponse coupée par le modèle (contexte plein)")
            content = (content.strip() or "…") + TRUNCATED_NOTE
        calls = message.get("tool_calls") or _inline_tool_calls(content)
        if not calls and extract_code(content):
            return AgentResult(content.strip(), actions, trace, errors)   # code à faire confirmer
        if not calls:
            nudge = None
            if not nudged and ctx.is_owner:
                if _ANNOUNCES_ACTION.search(content.strip()):
                    nudge = NUDGE
                elif not actions and not acted and _CLAIMS_ACTION.search(content):
                    nudge = CLAIM_NUDGE
            if nudge:
                nudged = True
                messages += [{"role": "assistant", "content": content},
                             {"role": "user", "content": nudge}]
                continue
            if not actions and not acted and _CLAIMS_ACTION.search(content):
                Log.warning("Le modèle prétend avoir agi sans appeler d'outil")
                content += "\n\n⚠️ (Aucune action n'a réellement été effectuée.)"
            return AgentResult(content.strip(), actions, trace, errors)

        call_message = {"role": "assistant", "content": "", "tool_calls": calls}
        messages.append(call_message)
        trace.append(call_message)
        for call in calls:
            function = call.get("function", {})
            name = function.get("name", "")
            result = await execute(ctx, name, function.get("arguments"))
            actions.append(f"{name} → {result.splitlines()[0][:120] if result else ''}")
            if result.startswith("Erreur"):
                error = result.split(":", 1)[-1].strip().splitlines()[0][:200]
                Log.warning(f"Outil {name} en échec : {error}")
                errors.append(f"{name} : {error}")
            messages.append({"role": "tool", "content": result, "tool_name": name})
            trace.append({"role": "tool", "content": result[:TRACE_RESULT_CHARS], "tool_name": name})

    return AgentResult("J'ai enchaîné trop d'étapes sans finir, je m'arrête là.", actions, trace, errors)
