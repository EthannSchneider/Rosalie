"""Initiative de Rosalie : se taire, revenir plus tard, ou écrire d'elle-même.

Tout ce qui est « décision » ici est pur (sans Discord) pour être testable.
"""
import datetime
import re

SILENCE = "[SILENCE]"
_SILENCE = re.compile(r"^\W*\[?\s*silence\s*\]?\W*$", re.IGNORECASE)


def is_silence(reply: str) -> bool:
    """Le modèle a choisi de ne rien dire (réponse vide ou [SILENCE])."""
    text = (reply or "").strip()
    return not text or text == "…" or bool(_SILENCE.match(text)) or text.upper().startswith(SILENCE)


def parse_hours(raw: str) -> tuple[int, int] | None:
    """« 23-8 » -> (23, 8). Vide/invalide -> None (pas d'heures calmes)."""
    try:
        start, end = (int(part) % 24 for part in raw.split("-"))
    except (ValueError, AttributeError):
        return None
    return None if start == end else (start, end)


def in_quiet_hours(now: datetime.datetime, quiet: tuple[int, int] | None) -> bool:
    if not quiet:
        return False
    start, end = quiet
    hour = now.hour
    return start <= hour < end if start < end else hour >= start or hour < end


def reflection_skip_reason(now: float, *, enabled: bool, quiet: tuple[int, int] | None,
                           last_activity: float, last_reflection: float,
                           last_was_spontaneous: bool, initiatives_today: int,
                           every_minutes: int, min_silence_minutes: int,
                           max_per_day: int) -> str | None:
    """None = elle peut réfléchir à écrire d'elle-même ; sinon la raison de s'abstenir."""
    if not enabled:
        return "initiative désactivée"
    if in_quiet_hours(datetime.datetime.fromtimestamp(now), quiet):
        return "heures calmes"
    if now - last_reflection < every_minutes * 60:
        return "a réfléchi récemment"
    if now - last_activity < min_silence_minutes * 60:
        return "conversation récente"
    if last_was_spontaneous:
        return "son dernier message spontané est resté sans réponse"
    if initiatives_today >= max_per_day:
        return "quota du jour atteint"
    return None


def _ago(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} jours"


def followup_note(intention: str, created: float, now: float) -> str:
    return (f"(Note système — personne ne t'a écrit : c'est le moment de la relance que tu avais "
            f"prévue il y a {_ago(now - created)} : « {intention} ». "
            "Relis la conversation. Si c'est toujours pertinent, écris ton message maintenant "
            "(tu peux utiliser tes outils avant). Si ce n'est plus utile (déjà fait, il a répondu "
            f"entre-temps…), réponds exactement {SILENCE}.)")


def reflection_note(last_activity: float, now: float, speaker: str) -> str:
    since = f"Le dernier message ici date d'il y a {_ago(now - last_activity)}." if last_activity \
        else "Vous n'avez encore jamais parlé ici."
    return (f"(Note système — moment de réflexion, personne ne t'a écrit. {since} "
            f"Tu peux écrire de toi-même à {speaker} SI tu as une vraie raison : prendre des "
            "nouvelles d'un truc dont il t'a parlé (examen, projet, rendez-vous…), un souvenir "
            "daté d'aujourd'hui, une idée ou une info qui l'intéresserait, ou simplement une "
            "envie sincère de lui parler. Sois naturelle et brève, ne fais pas semblant qu'il "
            "t'a écrit. La plupart du temps il n'y a rien à dire : dans ce cas réponds "
            f"exactement {SILENCE}.)")


def with_note(messages: list[dict], note: str) -> list[dict]:
    """Ajoute une note système en fin de conversation (rôle user, sans casser l'alternance)."""
    last = messages[-1]
    if last["role"] == "user" and "tool_calls" not in last:
        last["content"] += "\n\n" + note
    else:
        messages.append({"role": "user", "content": note})
    return messages
