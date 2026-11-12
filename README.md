# Rosalie

Rosalie est l'assistante personnelle de son créateur : elle discute avec une vraie personnalité,
**agit** quand tu lui demandes (Discord, internet, photos, code confirmé), **se souvient** de ce
qui compte et peut **prendre l'initiative** de t'écrire. Elle tourne en local avec Ollama.

Discord n'est qu'une **interface** : le cœur de Rosalie ne dépend d'aucune messagerie, et on
peut lui en ajouter d'autres (le terminal en est déjà une).

```bash
cp .env.example .env                  # ROSALIE_TOKEN, OWNER_IDS…
pip install -r requirements.txt
python bot.py                         # interfaces de INTERFACES (défaut : discord)
python bot.py chat                    # discuter dans le terminal, sans Discord
python bot.py test
```

📚 **Documentation complète : [`docs/`](docs/README.md)** — [architecture](docs/architecture.md),
[installation](docs/installation.md), [utilisation](docs/utilisation.md),
[fonctionnalités](docs/fonctionnalites.md), [développement](docs/developpement.md).
