import json
import time
from pathlib import Path


class DatasetStore:
    """Collecte des exemples d'entraînement (format chat mlx-lm) depuis Discord."""

    def __init__(self, path: Path):
        self.path = path

    def add(self, messages: list[dict], reply: str, source: str, channel_id: int):
        if not messages or not reply.strip():
            return
        sample = {
            "messages": [*messages, {"role": "assistant", "content": reply.strip()}],
            "meta": {"source": source, "channel_id": channel_id, "time": int(time.time())},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(sample, ensure_ascii=False) + "\n")

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open(encoding="utf-8") as file:
            return sum(1 for line in file if line.strip())
