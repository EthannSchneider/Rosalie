import datetime
import json

from libs.llm.ollama import OllamaClient, OllamaError
from libs.log import Log
from libs.memory.long_term import LongTermMemory

PROMPT = """Tu extrais des souvenirs durables d'une conversation entre {speaker} et Rosalie (une IA).

Garde UNIQUEMENT les informations utiles des semaines plus tard :
faits sur {speaker} ou ses proches (noms, animaux, dates, lieux, travail), préférences, projets,
décisions, demandes permanentes (« à partir de maintenant… »), moments émotionnels importants.
Ignore : salutations, questions, actions ponctuelles sur Discord, banalités, ce qui est déjà connu.

Déjà connu :
{known}

Nous sommes le {today}. Convertis les dates relatives (« lundi », « demain ») en dates précises.
Écris chaque souvenir à la 3e personne avec les noms (ex : « Le chat d'Ethann s'appelle Minou »).
Réponds en JSON : {{"memories": [{{"content": "...", "category": "personne|préférence|projet|événement|ressenti|autre", "importance": 1-5}}]}}
Liste vide si rien ne mérite d'être retenu."""

SCHEMA = {
    "type": "object",
    "properties": {"memories": {"type": "array", "items": {
        "type": "object",
        "properties": {"content": {"type": "string"}, "category": {"type": "string"},
                       "importance": {"type": "integer"}},
        "required": ["content"]}}},
    "required": ["memories"],
}


DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _today() -> str:
    """Date du jour + calendrier des 7 prochains jours (les LLM calculent mal les dates)."""
    today = datetime.date.today()
    upcoming = ", ".join(
        f"{DAYS[day.weekday()]} = {day:%d.%m.%Y}"
        for day in (today + datetime.timedelta(days=offset) for offset in range(1, 8)))
    return f"{DAYS[today.weekday()]} {today:%d.%m.%Y} (prochains jours : {upcoming})"


async def extract_memories(llm: OllamaClient, model: str, long_term: LongTermMemory,
                           speaker: str, user_text: str, reply: str) -> list[int]:
    """Appel LLM en arrière-plan : note les faits durables du dernier échange."""
    known = await long_term.search(user_text, limit=5, min_score=0.5)
    try:
        raw = await llm.chat(
            [{"role": "system", "content": PROMPT.format(
                today=_today(), speaker=speaker, known="\n".join(m.content for m in known) or "(rien)")},
             {"role": "user", "content": f"{speaker}: {user_text}\nRosalie: {reply}"}],
            model=model, format=SCHEMA, options={"temperature": 0, "num_predict": 300})
        items = json.loads(raw).get("memories", [])
    except (OllamaError, json.JSONDecodeError, AttributeError) as error:
        Log.warning(f"Memory extraction failed: {error}")
        return []

    ids = []
    for item in items[:5]:
        content = str(item.get("content", "")).strip()
        if len(content) < 8:
            continue
        importance = item.get("importance", 3)
        memory_id, updated = await long_term.add(
            content, str(item.get("category") or "autre"),
            importance if isinstance(importance, int) else 3)
        ids.append(memory_id)
        Log.info(f"Memory #{memory_id} {'updated' if updated else 'saved'}: {content}")
    return ids
