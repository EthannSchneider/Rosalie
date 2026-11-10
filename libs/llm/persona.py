from pathlib import Path

from libs.log import Log


DEFAULT_PERSONA = "Tu es Gideon, une IA qui joue un personnage sur Discord. Reste en personnage."


class Persona:
    """Charge le prompt système du personnage depuis un fichier Markdown."""

    def __init__(self, path: Path):
        self.path = path
        self.text = DEFAULT_PERSONA
        self.reload()

    def reload(self) -> str:
        try:
            self.text = self.path.read_text(encoding="utf-8").strip() or DEFAULT_PERSONA
        except FileNotFoundError:
            Log.warning(f"Persona file {self.path} not found, using default persona")
        return self.text
