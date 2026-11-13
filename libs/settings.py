import json
from pathlib import Path


class Settings:
    """État choisi depuis les interfaces (/rosalie here), persisté en JSON.

    Les réglages proprement dits sont dans storages/config.sqlite3 (libs/config). Les anciennes
    clés « model » et « initiative » de ce fichier y sont importées au premier lancement.
    """

    def __init__(self, path: Path):
        self.__path = path
        self.__data = {"dedicated": []}
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
