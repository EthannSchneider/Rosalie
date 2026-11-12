import json
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Entry:
    author_id: int | str
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
    """Historique court terme par conversation (fenêtre glissante), persisté en JSON.
    Une conversation = sa clé « interface:id » (ex : « discord:123 », « terminal:local »)."""

    def __init__(self, directory: Path, max_size: int = 30):
        self.__directory = directory
        self.__max_size = max_size
        self.__channels: dict[str, deque[Entry]] = {}

    def __file(self, key: str) -> Path:
        return self.__directory / f"{str(key).replace(':', '_')}.json"

    def __legacy(self, key: str) -> Path | None:
        """Ancien format : un salon Discord stocké sous « <id>.json »."""
        interface, _, native_id = str(key).partition(":")
        return self.__directory / f"{native_id}.json" if interface == "discord" else None

    def __load(self, key: str) -> deque[Entry]:
        if key not in self.__channels:
            entries: deque[Entry] = deque(maxlen=self.__max_size)
            path = self.__file(key)
            legacy = self.__legacy(key)
            if not path.exists() and legacy is not None and legacy.exists():
                legacy.rename(path)
            if path.exists():
                try:
                    for raw in json.loads(path.read_text(encoding="utf-8")):
                        entries.append(Entry(**raw))
                except (json.JSONDecodeError, TypeError):
                    pass
            self.__channels[key] = entries
        return self.__channels[key]

    def __save(self, key: str):
        self.__directory.mkdir(parents=True, exist_ok=True)
        data = [asdict(entry) for entry in self.__channels.get(key, [])]
        self.__file(key).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def add(self, key: str, entry: Entry):
        self.__load(key).append(entry)
        self.__save(key)

    def get(self, key: str) -> list[Entry]:
        return list(self.__load(key))

    def before(self, key: str, message_id: int) -> tuple[list[Entry], Entry | None]:
        """Retourne (contexte avant le message, l'entrée du message)."""
        entries = self.get(key)
        for index, entry in enumerate(entries):
            if entry.message_id == message_id:
                return entries[:index], entry
        return entries, None

    def replace_content(self, key: str, message_id: int, content: str) -> bool:
        for entry in self.__load(key):
            if entry.message_id == message_id:
                entry.content = content
                self.__save(key)
                return True
        return False

    def clear(self, key: str):
        self.__channels[key] = deque(maxlen=self.__max_size)
        self.__file(key).unlink(missing_ok=True)
