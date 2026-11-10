import json
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from libs.llm.ollama import OllamaClient, OllamaError
from libs.log import Log


@dataclass
class Memory:
    id: int
    content: str
    category: str
    importance: int
    created_at: float
    score: float = 0.0

    def line(self) -> str:
        date = time.strftime("%d.%m.%Y", time.localtime(self.created_at))
        return f"#{self.id} [{self.category}, {date}] {self.content}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class LongTermMemory:
    """Mémoire à long terme de Rosalie : des notes en SQLite + recherche sémantique.

    - les souvenirs importants (importance >= 4) sont toujours dans son prompt
    - à chaque message, les souvenirs proches du sujet sont injectés automatiquement
    - elle peut aussi noter / chercher / oublier elle-même via les outils
      remember / recall / forget
    """

    DUPLICATE_THRESHOLD = 0.93

    def __init__(self, path: Path, llm: OllamaClient, embed_model: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.__db = sqlite3.connect(path)
        self.__db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'général',
                importance INTEGER NOT NULL DEFAULT 3,
                created_at REAL NOT NULL,
                embedding TEXT
            )""")
        self.__db.commit()
        self.__llm = llm
        self.__embed_model = embed_model

    async def __embed(self, text: str, kind: str) -> list[float] | None:
        # nomic-embed-text attend ces préfixes ; sans effet gênant pour les autres modèles
        prefix = "search_query: " if kind == "query" else "search_document: "
        try:
            vectors = await self.__llm.embed([prefix + text], self.__embed_model)
            return vectors[0] if vectors else None
        except OllamaError as error:
            Log.warning(f"Embedding failed ({error}), falling back to keyword search")
            return None

    def __rows(self, sql: str, params=()) -> list[tuple]:
        return self.__db.execute(sql, params).fetchall()

    @staticmethod
    def __memory(row, score=0.0) -> Memory:
        return Memory(row[0], row[1], row[2], row[3], row[4], score)

    async def add(self, content: str, category: str = "général", importance: int = 3) -> tuple[int, bool]:
        """Ajoute un souvenir. Retourne (id, updated) — updated si un quasi-doublon a été remplacé."""
        content = content.strip()
        importance = max(1, min(5, int(importance)))
        embedding = await self.__embed(content, "document")
        if embedding:
            for memory in await self.search(content, limit=1, min_score=self.DUPLICATE_THRESHOLD):
                self.__db.execute(
                    "UPDATE memories SET content=?, category=?, importance=MAX(importance, ?), "
                    "created_at=?, embedding=? WHERE id=?",
                    (content, category, importance, time.time(), json.dumps(embedding), memory.id))
                self.__db.commit()
                return memory.id, True
        cursor = self.__db.execute(
            "INSERT INTO memories (content, category, importance, created_at, embedding) "
            "VALUES (?, ?, ?, ?, ?)",
            (content, category, importance, time.time(),
             json.dumps(embedding) if embedding else None))
        self.__db.commit()
        return cursor.lastrowid, False

    async def search(self, query: str, limit: int = 5, min_score: float = 0.45) -> list[Memory]:
        query_vector = await self.__embed(query, "query")
        rows = self.__rows("SELECT id, content, category, importance, created_at, embedding FROM memories")
        if query_vector:
            scored = [self.__memory(row, _cosine(query_vector, json.loads(row[5])))
                      for row in rows if row[5]]
            scored = [memory for memory in scored if memory.score >= min_score]
        else:
            words = {word for word in query.lower().split() if len(word) > 3}
            scored = [self.__memory(row, sum(word in row[1].lower() for word in words))
                      for row in rows]
            scored = [memory for memory in scored if memory.score > 0]
        scored.sort(key=lambda memory: (memory.score, memory.importance), reverse=True)
        return scored[:limit]

    def core(self, limit: int = 15) -> list[Memory]:
        """Souvenirs importants, toujours présents dans le prompt."""
        rows = self.__rows(
            "SELECT id, content, category, importance, created_at FROM memories "
            "WHERE importance >= 4 ORDER BY importance DESC, created_at DESC LIMIT ?", (limit,))
        return [self.__memory(row) for row in rows]

    def recent(self, limit: int = 20, offset: int = 0) -> list[Memory]:
        rows = self.__rows(
            "SELECT id, content, category, importance, created_at FROM memories "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
        return [self.__memory(row) for row in rows]

    def forget(self, memory_id: int) -> bool:
        cursor = self.__db.execute("DELETE FROM memories WHERE id=?", (int(memory_id),))
        self.__db.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        return self.__rows("SELECT COUNT(*) FROM memories")[0][0]

    def close(self):
        self.__db.close()
