# Rosalie

Rosalie est l'assistante personnelle de son créateur : elle discute avec une vraie personnalité,
**agit** quand tu lui demandes (Discord, internet, photos, code confirmé), **se souvient** de ce
qui compte et peut **prendre l'initiative** de t'écrire. Elle tourne en local avec Ollama.

Discord n'est qu'une **interface** : le cœur de Rosalie ne dépend d'aucune messagerie, et on
peut lui en ajouter d'autres (le terminal en est déjà une).

```bash
pip install -r requirements.txt
npm --prefix webui install && npm --prefix webui run build   # le site web
python bot.py                         # puis http://127.0.0.1:8765 : crée le superadmin
python bot.py chat                    # discuter dans le terminal, sans Discord
python bot.py test
```

📚 **Documentation complète : [`docs/`](docs/README.md)** — [architecture](docs/architecture.md),
[installation](docs/installation.md), [site web](docs/site-web.md), [réglages](docs/reglages.md), [utilisation](docs/utilisation.md),
[fonctionnalités](docs/fonctionnalites.md), [développement](docs/developpement.md).
