import json
from pathlib import Path


class Settings:
    """Réglages modifiables à chaud depuis Discord, persistés en JSON.

    Les valeurs du .env restent la base ; celles-ci s'y ajoutent.
    """

    def __init__(self, path: Path):
        self.__path = path
        self.__data = {"channel_ids": [], "model": None}
        if path.exists():
            self.__data.update(json.loads(path.read_text(encoding="utf-8")))

    def __save(self):
        self.__path.parent.mkdir(parents=True, exist_ok=True)
        self.__path.write_text(json.dumps(self.__data, indent=2), encoding="utf-8")

    @property
    def channel_ids(self) -> set[int]:
        return set(self.__data["channel_ids"])

    def toggle_channel(self, channel_id: int) -> bool:
        """Ajoute/retire un salon dédié. Retourne True s'il est maintenant actif."""
        ids = self.channel_ids
        if channel_id in ids:
            ids.remove(channel_id)
            enabled = False
        else:
            ids.add(channel_id)
            enabled = True
        self.__data["channel_ids"] = sorted(ids)
        self.__save()
        return enabled

    @property
    def initiative(self) -> bool | None:
        """None = valeur du .env (INITIATIVE)."""
        return self.__data.get("initiative")

    @initiative.setter
    def initiative(self, value: bool | None):
        self.__data["initiative"] = value
        self.__save()

    @property
    def model(self) -> str | None:
        return self.__data.get("model")

    @model.setter
    def model(self, value: str | None):
        self.__data["model"] = value
        self.__save()
