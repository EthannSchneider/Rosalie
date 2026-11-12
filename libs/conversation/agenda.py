"""Agenda de Rosalie : ses relances programmées et l'état de son initiative, persistés en JSON.

Une relance (« followup ») = « dans X minutes, je reviens vers lui à propos de … ».
Le heartbeat (cogs/rosalie/heartbeat.py) les déclenche quand elles arrivent à échéance.
"""
import datetime
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Followup:
    id: int
    channel_id: int
    user_id: int
    due: float                 # timestamp
    intention: str             # ce qu'elle compte faire/dire
    created: float = field(default_factory=time.time)

    def line(self, now: float | None = None) -> str:
        when = datetime.datetime.fromtimestamp(self.due)
        delta = max(0, round((self.due - (now or time.time())) / 60))
        return f"#{self.id} à {when:%d.%m %H:%M} (dans {delta} min) : {self.intention}"


class Agenda:
    def __init__(self, path: Path):
        self.__path = path
        self.__data = {"next_id": 1, "followups": [], "home": None,
                       "last_reflection": 0.0, "initiatives": []}
        if path.exists():
            try:
                self.__data.update(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        self.__followups = [Followup(**raw) for raw in self.__data["followups"]]

    def __save(self):
        self.__data["followups"] = [asdict(f) for f in self.__followups]
        self.__path.parent.mkdir(parents=True, exist_ok=True)
        self.__path.write_text(json.dumps(self.__data, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    # --- relances ------------------------------------------------------------
    def add(self, channel_id: int, user_id: int, delay_seconds: float, intention: str,
            now: float | None = None) -> Followup:
        followup = Followup(self.__data["next_id"], channel_id, user_id,
                            (now or time.time()) + delay_seconds, intention.strip())
        self.__data["next_id"] += 1
        self.__followups.append(followup)
        self.__save()
        return followup

    def cancel(self, followup_id: int) -> bool:
        before = len(self.__followups)
        self.__followups = [f for f in self.__followups if f.id != followup_id]
        if len(self.__followups) != before:
            self.__save()
            return True
        return False

    def pop_due(self, now: float | None = None) -> list[Followup]:
        """Retire et renvoie les relances arrivées à échéance (une seule exécution garantie)."""
        now = now or time.time()
        due = [f for f in self.__followups if f.due <= now]
        if due:
            self.__followups = [f for f in self.__followups if f.due > now]
            self.__save()
        return sorted(due, key=lambda f: f.due)

    def pending(self, channel_id: int | None = None) -> list[Followup]:
        return sorted((f for f in self.__followups
                       if channel_id is None or f.channel_id == channel_id), key=lambda f: f.due)

    # --- initiative ------------------------------------------------------------
    @property
    def home(self) -> tuple[int, int] | None:
        """(salon, owner) de la dernière conversation avec un owner : là où elle prend l'initiative."""
        home = self.__data.get("home")
        return (home[0], home[1]) if home else None

    def set_home(self, channel_id: int, user_id: int):
        if self.home != (channel_id, user_id):
            self.__data["home"] = [channel_id, user_id]
            self.__save()

    @property
    def last_reflection(self) -> float:
        return float(self.__data.get("last_reflection") or 0)

    def mark_reflection(self, now: float | None = None):
        self.__data["last_reflection"] = now or time.time()
        self.__save()

    def mark_initiative(self, now: float | None = None):
        now = now or time.time()
        self.__data["initiatives"] = [t for t in self.__data["initiatives"] if now - t < 86400] + [now]
        self.__save()

    def initiatives_since(self, since: float) -> int:
        return sum(1 for t in self.__data["initiatives"] if t >= since)
