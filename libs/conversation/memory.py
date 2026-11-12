import json
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Entry:
    author_id: int
    author_name: str
    content: str
    is_bot: bool
    message_id: int = 0
    acted: bool = False  # la réponse a déclenché des outils (exclue du fine-tuning)
    # Appels d'outils faits avant cette réponse (ce qui a vraiment été envoyé, à qui…)
    tool_messages: list[dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    spontaneous: bool = False  # message écrit de sa propre initiative (personne ne lui avait parlé)


class ConversationMemory:
    """Historique court terme par salon (fenêtre glissante), persisté en JSON."""

    def __init__(self, directory: Path, max_size: int = 30):
        self.__directory = directory
        self.__max_size = max_size
        self.__channels: dict[int, deque[Entry]] = {}

    def __file(self, channel_id: int) -> Path:
        return self.__directory / f"{channel_id}.json"

    def __load(self, channel_id: int) -> deque[Entry]:
        if channel_id not in self.__channels:
            entries: deque[Entry] = deque(maxlen=self.__max_size)
            path = self.__file(channel_id)
            if path.exists():
                try:
                    for raw in json.loads(path.read_text(encoding="utf-8")):
                        entries.append(Entry(**raw))
                except (json.JSONDecodeError, TypeError):
                    pass
            self.__channels[channel_id] = entries
        return self.__channels[channel_id]

    def __save(self, channel_id: int):
        self.__directory.mkdir(parents=True, exist_ok=True)
        data = [asdict(entry) for entry in self.__channels.get(channel_id, [])]
        self.__file(channel_id).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def add(self, channel_id: int, entry: Entry):
        self.__load(channel_id).append(entry)
        self.__save(channel_id)

    def get(self, channel_id: int) -> list[Entry]:
        return list(self.__load(channel_id))

    def before(self, channel_id: int, message_id: int) -> tuple[list[Entry], Entry | None]:
        """Retourne (contexte avant le message, l'entrée du message)."""
        entries = self.get(channel_id)
        for index, entry in enumerate(entries):
            if entry.message_id == message_id:
                return entries[:index], entry
        return entries, None

    def replace_content(self, channel_id: int, message_id: int, content: str) -> bool:
        for entry in self.__load(channel_id):
            if entry.message_id == message_id:
                entry.content = content
                self.__save(channel_id)
                return True
        return False

    def clear(self, channel_id: int):
        self.__channels[channel_id] = deque(maxlen=self.__max_size)
        self.__file(channel_id).unlink(missing_ok=True)
