import json
import re
from dataclasses import dataclass, field

from libs.assistant.tools import TOOLS, ToolContext, execute, schemas
from libs.llm.ollama import OllamaClient


@dataclass
class AgentResult:
    text: str
    actions: list[str] = field(default_factory=list)


_INLINE_CALL = re.compile(r"^\s*(\{.*\})\s*$", re.DOTALL)

# « Je vais vérifier… », « Laisse-moi regarder… » : le modèle annonce une action puis s'arrête
_ANNOUNCES_ACTION = re.compile(
    r"^\W*(je vais|je m'en occupe|laisse-moi|attends|je regarde|je vérifie|je cherche|"
    r"un instant|une seconde|je lis)\b", re.IGNORECASE)
NUDGE = ("(Note système : tu viens d'annoncer une action sans la faire. Fais-la maintenant "
         "avec les outils, puis donne ta réponse finale.)")


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
                    max_steps: int = 6) -> AgentResult:
    """Boucle « le modèle appelle des outils -> on lui renvoie les résultats »
    jusqu'à ce qu'il produise une réponse finale en texte."""
    actions: list[str] = []
    tools = schemas(getattr(ctx.bot.config, "web_access", True))
    nudged = False
    for _ in range(max_steps):
        message = await llm.chat_message(messages, tools=tools)
        content = message.get("content", "") or ""
        calls = message.get("tool_calls") or _inline_tool_calls(content)
        if not calls:
            if not nudged and _ANNOUNCES_ACTION.search(content.strip()):
                nudged = True
                messages += [{"role": "assistant", "content": content},
                             {"role": "user", "content": NUDGE}]
                continue
            return AgentResult(content.strip(), actions)

        messages.append({"role": "assistant", "content": "", "tool_calls": calls})
        for call in calls:
            function = call.get("function", {})
            name = function.get("name", "")
            result = await execute(ctx, name, function.get("arguments"))
            actions.append(f"{name} → {result.splitlines()[0][:120] if result else ''}")
            messages.append({"role": "tool", "content": result, "tool_name": name})

    return AgentResult("J'ai enchaîné trop d'étapes sans finir, je m'arrête là.", actions)
