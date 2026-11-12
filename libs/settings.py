import json
from pathlib import Path


class Settings:
    """Réglages modifiables à chaud depuis Discord, persistés en JSON.

    Les valeurs du .env restent la base ; celles-ci s'y ajoutent.
    """

    def __init__(self, path: Path):
        self.__path = path
        self.__data = {"dedicated": [], "model": None}
        if path.exists():
            self.__data.update(json.loads(path.read_text(encoding="utf-8")))
        # Ancien format : ids de salons Discord
        legacy = self.__data.pop("channel_ids", [])
        self.__data["dedicated"] = sorted(set(self.__data["dedicated"]) | {f"discord:{i}" for i in legacy})

    def __save(self):
        self.__path.parent.mkdir(parents=True, exist_ok=True)
        self.__path.write_text(json.dumps(self.__data, indent=2), encoding="utf-8")

    @property
    def dedicated(self) -> set[str]:
        """Conversations dédiées (clés « interface:id ») : elle y répond à tout."""
        return set(self.__data["dedicated"])

    def toggle_dedicated(self, key: str) -> bool:
        """Ajoute/retire une conversation dédiée. Retourne True si elle l'est maintenant."""
        keys = self.dedicated
        enabled = key not in keys
        keys.symmetric_difference_update({key})
        self.__data["dedicated"] = sorted(keys)
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
