"""Transforme un historique de conversation privée (Discord ou WhatsApp) en exemples
d'entraînement au format chat de mlx-lm.

- tri chronologique, découpage en conversations quand il y a une longue pause
- messages consécutifs d'une même personne fusionnés en un seul tour
- mentions, liens, e-mails et numéros de téléphone neutralisés
- médias, appels, messages supprimés et messages système ignorés
- un exemple par réponse de « l'assistant », avec les tours précédents comme contexte
"""
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SESSION_GAP = 3 * 3600               # secondes sans message => nouvelle conversation
CONTEXT_TURNS = 8                    # tours gardés avant chaque réponse
MAX_SAMPLE_CHARS = 6000

_URL = re.compile(r"https?://\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+|00)?\d[\d \-.]{7,}\d(?!\d)")
_MENTION = re.compile(r"<@!?(\d+)>")
_CUSTOM_EMOJI = re.compile(r"<a?(:\w+:)\d+>")


@dataclass
class Message:
    author: str      # identifiant stable de l'auteur (id Discord ou nom WhatsApp)
    text: str
    time: float


@dataclass
class Turn:
    author: str
    text: str
    time: float


def clean(text: str, names: dict[str, str] | None = None) -> str:
    names = names or {}
    text = _MENTION.sub(lambda m: "@" + names.get(m.group(1), "quelqu'un"), text)
    text = _CUSTOM_EMOJI.sub(r"\1", text)
    text = _URL.sub("[lien]", text)
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[téléphone]", text)
    return text.strip()


# --------------------------------------------------------------------------- Discord

DISCORD_TEXT_TYPES = {0, 19}         # message normal, réponse


def load_discord(path: Path) -> list[Message]:
    """messages.txt de finetune/collect/export_discord.py : un message JSON de l'API par ligne."""
    raw = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                message = json.loads(line)
                raw[message["id"]] = message   # dédoublonne si le script a été relancé
    ordered = sorted(raw.values(), key=lambda m: int(m["id"]))
    names = {m["author"]["id"]: m["author"].get("global_name") or m["author"]["username"]
             for m in ordered}
    messages = []
    for message in ordered:
        if message.get("type", 0) not in DISCORD_TEXT_TYPES:
            continue
        text = clean(message.get("content", ""), names)
        if text:
            time = datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00")).timestamp()
            messages.append(Message(message["author"]["id"], text, time))
    return messages


# --------------------------------------------------------------------------- WhatsApp

# iOS     : [26.05.2021, 07:33:12] Nom: texte
# Android : 26.05.21, 07:33 - Nom: texte   (ou 26/05/2021, 07:33 - Nom: texte)
_WA_IOS = re.compile(r"^‎?\[(\d{1,2})[./](\d{1,2})[./](\d{2,4}),? (\d{1,2}):(\d{2})(?::(\d{2}))?\] ([^:]+): ?(.*)$")
_WA_ANDROID = re.compile(r"^‎?(\d{1,2})[./](\d{1,2})[./](\d{2,4}),? (\d{1,2}):(\d{2})(?::(\d{2}))? - ([^:]+): ?(.*)$")
_WA_MEDIA = re.compile(
    r"‎?(?:image|sticker|audio|video|GIF|video note|document|Contact card|photo|"
    r"image absente|vidéo absente|audio omis|autocollant omis|GIF retiré)\s+(?:omitted|omis|absente?)|"
    r"<attached: [^>]*>|<Media omitted>|<Médias omis>|‎?<This message was edited>|"
    r"‎?<Ce message a été modifié>", re.IGNORECASE)
_WA_SKIP = re.compile(
    r"^(This message was deleted\.?|You deleted this message\.?|Ce message a été supprimé\.?|"
    r"Vous avez supprimé ce message\.?|Messages and calls are end-to-end encrypted.*|"
    r"Les messages et les appels sont chiffrés.*|(Missed |Silenced )?(voice|video) call.*|"
    r"Appel (vocal|vidéo).*|Location: .*|Position : .*|.*\.vcf.*)$", re.IGNORECASE | re.DOTALL)


def _wa_read(path: Path) -> str:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".txt"))
            return archive.read(name).decode("utf-8", errors="replace")
    return path.read_text(encoding="utf-8", errors="replace")


def _wa_text(body: str) -> str:
    body = _WA_MEDIA.sub("", body).replace("‎", "").replace(" ", " ").strip()
    if not body or _WA_SKIP.match(body):
        return ""
    return clean(body)


def load_whatsapp(path: Path) -> list[Message]:
    """Export « Exporter la discussion » de WhatsApp (.zip ou _chat.txt)."""
    entries: list[list] = []   # [auteur, corps, time]
    for line in _wa_read(path).splitlines():
        match = _WA_IOS.match(line) or _WA_ANDROID.match(line)
        if match:
            day, month, year, hour, minute, second, author, body = match.groups()
            year = int(year) + (2000 if len(year) == 2 else 0)
            time = datetime(year, int(month), int(day), int(hour), int(minute), int(second or 0)).timestamp()
            entries.append([author.strip("‎ ").strip(), body, time])
        elif entries:                     # suite d'un message sur plusieurs lignes
            entries[-1][1] += "\n" + line
    messages = []
    for author, body, time in entries:
        text = _wa_text(body)
        if text:
            messages.append(Message(author, text, time))
    return messages


def whatsapp_authors(path: Path) -> set[str]:
    authors = set()
    for line in _wa_read(path).splitlines():
        match = _WA_IOS.match(line) or _WA_ANDROID.match(line)
        if match:
            authors.add(match.group(7).strip("‎ ").strip())
    return authors


# --------------------------------------------------------------------------- conversion

def to_turns(messages: list[Message]) -> list[list[Turn]]:
    """Messages -> conversations (listes de tours alternés)."""
    sessions: list[list[Turn]] = []
    last_time = None
    for message in messages:
        if last_time is None or message.time - last_time > SESSION_GAP:
            sessions.append([])
        last_time = message.time
        session = sessions[-1]
        if session and session[-1].author == message.author:
            session[-1].text += "\n" + message.text
            session[-1].time = message.time
        else:
            session.append(Turn(message.author, message.text, message.time))
    return [session for session in sessions if len(session) >= 2]


def to_samples(sessions: list[list[Turn]], assistant: str) -> list[dict]:
    samples = []
    for session in sessions:
        for index, turn in enumerate(session):
            if turn.author != assistant or index == 0:
                continue
            context = session[max(0, index - CONTEXT_TURNS):index]
            while context and context[0].author == assistant:   # commencer par l'humain
                context = context[1:]
            if not context:
                continue
            messages = [{"role": "assistant" if t.author == assistant else "user", "content": t.text}
                        for t in context + [turn]]
            while sum(len(m["content"]) for m in messages) > MAX_SAMPLE_CHARS and len(messages) > 2:
                messages = messages[2:]   # retire le plus vieux couple user/assistant
            samples.append({"messages": messages})
    return samples


def write_samples(messages: list[Message], output_path: Path, assistants: list[str]) -> tuple[int, int]:
    """Plusieurs assistants = un jeu d'exemples par point de vue. Retourne (conversations, exemples)."""
    sessions = to_turns(messages)
    samples = [sample for assistant in assistants for sample in to_samples(sessions, assistant)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for sample in samples:
            file.write(json.dumps(sample, ensure_ascii=False) + "\n")
    return len(sessions), len(samples)


def convert(messages_path: Path, output_path: Path, assistant_ids: list[str]) -> tuple[int, int]:
    """Discord : messages.txt -> dataset."""
    return write_samples(load_discord(messages_path), output_path, assistant_ids)
