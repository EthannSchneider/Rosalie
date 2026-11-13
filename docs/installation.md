# Installation

## Prérequis

- Python 3.13
- Node.js (seulement pour construire le site web)
- [Ollama](https://ollama.com), local ou sur un serveur
- Pour Discord : un bot créé dans le [Developer Portal](https://discord.com/developers/applications),
  avec **Message Content Intent** et **Server Members Intent** activés (onglet *Bot*)

## Étapes

```bash
cp .env.example .env          # démarrage seulement (dossier de données, adresse du site)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # navigateur virtuel (sites en JavaScript)
ollama pull qwen3:8b && ollama pull nomic-embed-text
npm --prefix webui install && npm --prefix webui run build   # le site web
```

Lance `python bot.py`, ouvre http://127.0.0.1:8765 et crée le **superadmin** avec le code
d'installation affiché dans la console ([détails](site-web.md)). Ensuite :

1. *Réglages → Discord* : le token du bot ;
2. *Mon compte* : ton identifiant Discord (clic droit sur ton profil → *Copier l'identifiant*,
   mode développeur requis). Sur Discord, Rosalie n'agit que pour les comptes liés dont le rôle
   a la permission `act` ; les autres peuvent seulement discuter (`public_replies`).

Ou dans le terminal :

```bash
python bot.py users add ethann --role superadmin --discord <ton id>
python bot.py settings set discord_token        # demandé sans écho
```

- Tous les réglages et leur aide : [Réglages](reglages.md). Un ancien `.env` complet est
  importé automatiquement au premier lancement.

## Lancer

| Commande | Effet |
|---|---|
| `python bot.py` | lance Rosalie avec toutes ses interfaces sauf le terminal : Discord et le site web |
| `python bot.py chat` | discute avec elle dans le terminal, sans Discord |
| `python bot.py settings …` | voir / modifier les réglages ([détails](reglages.md)) |
| `python bot.py web` | seulement le site (réglages, comptes ; pas de chat) |
| `python bot.py users …` | gérer les comptes du site ([détails](site-web.md)) |
| `python bot.py pull [modèle]` | télécharge un modèle Ollama |
| `python bot.py test` | lance les tests |

Discord et le site tournent en même temps : c'est la même Rosalie (mêmes souvenirs, même agenda),
joignable des deux côtés. Sans token Discord, seul le site démarre (Rosalie le signale) : règle le
token puis relance. Le terminal a sa propre commande, `python bot.py chat`.

## Docker

```bash
docker compose -f deploy/docker/compose.yml up -d --build
```

Sur Mac, Ollama reste natif (pour le GPU) ; le conteneur le joint via `host.docker.internal`.
Le code qu'elle exécute tourne alors dans le conteneur. Le site est publié sur `127.0.0.1:8765` ;
le code d'installation est dans `docker compose … logs rosalie`. En ligne de commande : `docker compose -f deploy/docker/compose.yml exec rosalie python3 bot.py settings`.

## Le modèle

### Pourquoi qwen3:8b

Testé sur les mêmes demandes : **llama3.1:8b** appelle un outil pour tout (« Hello » →
envoie un message, « comment tu te sens » → change son statut). **qwen3:8b** (5,2 Go)
discute sans outil quand il faut et agit correctement quand on lui demande.

### La taille du contexte compte

`num_ctx` (réglage *Contexte*, ancien `OLLAMA_NUM_CTX`) est la « mémoire de travail » du modèle, en tokens. Elle doit contenir à chaque
message : la personnalité, les règles, la description des outils (~4 700 tokens avec Discord),
l'historique et les résultats d'outils. Trop petite, Ollama coupe des messages : réponses
tronquées (« Voici ce que… ») ou erreur `no user query found`.

- `num_ctx` à 16384 au minimum (défaut) ; 32768 si ta carte graphique le permet ;
- sur un serveur Ollama partagé, fixe aussi `OLLAMA_CONTEXT_LENGTH=16384` côté serveur, sinon un
  autre programme peut charger le modèle avec 2048 ;
- la page *Réglages → Outils* du site (ou `settings tools disable …`) retire les outils dont tu ne te sers pas (~100 tokens chacun).

Rosalie raccourcit d'elle-même les gros résultats d'outils et le plus vieil historique pour
tenir dans le contexte, et prévient si une réponse a quand même été coupée.
