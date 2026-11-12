# Installation

## Prérequis

- Python 3.13
- [Ollama](https://ollama.com), local ou sur un serveur
- Pour Discord : un bot créé dans le [Developer Portal](https://discord.com/developers/applications),
  avec **Message Content Intent** et **Server Members Intent** activés (onglet *Bot*)

## Étapes

```bash
cp .env.example .env          # puis remplis au moins ROSALIE_TOKEN et OWNER_IDS
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # navigateur virtuel (sites en JavaScript)
ollama pull qwen3:8b && ollama pull nomic-embed-text
```

- `OWNER_IDS` : ton id Discord (clic droit sur ton profil → *Copier l'identifiant*, mode
  développeur requis). Rosalie n'agit que pour ces personnes ; les autres peuvent seulement
  discuter (`PUBLIC_REPLIES`).
- Toutes les options sont commentées dans [`.env.example`](../.env.example).

## Lancer

| Commande | Effet |
|---|---|
| `python bot.py` | lance les interfaces de `INTERFACES` (par défaut : `discord`) |
| `python bot.py chat` | discute avec elle dans le terminal, sans Discord |
| `python bot.py pull [modèle]` | télécharge un modèle Ollama |
| `python bot.py test` | lance les tests |

`INTERFACES="discord,terminal"` lance les deux en même temps : c'est la même Rosalie (mêmes
souvenirs, même agenda), joignable des deux côtés.

## Docker

```bash
docker compose -f deploy/docker/compose.yml up -d --build
```

Sur Mac, Ollama reste natif (pour le GPU) ; le conteneur le joint via `host.docker.internal`.
Le code qu'elle exécute tourne alors dans le conteneur.

## Le modèle

### Pourquoi qwen3:8b

Testé sur les mêmes demandes : **llama3.1:8b** appelle un outil pour tout (« Hello » →
envoie un message, « comment tu te sens » → change son statut). **qwen3:8b** (5,2 Go)
discute sans outil quand il faut et agit correctement quand on lui demande.

### La taille du contexte compte

`OLLAMA_NUM_CTX` est la « mémoire de travail » du modèle, en tokens. Elle doit contenir à chaque
message : la personnalité, les règles, la description des outils (~4 700 tokens avec Discord),
l'historique et les résultats d'outils. Trop petite, Ollama coupe des messages : réponses
tronquées (« Voici ce que… ») ou erreur `no user query found`.

- `OLLAMA_NUM_CTX=16384` au minimum (défaut) ; 32768 si ta carte graphique le permet ;
- sur un serveur Ollama partagé, fixe aussi `OLLAMA_CONTEXT_LENGTH=16384` côté serveur, sinon un
  autre programme peut charger le modèle avec 2048 ;
- `DISABLED_TOOLS` retire les outils dont tu ne te sers pas (~100 tokens chacun).

Rosalie raccourcit d'elle-même les gros résultats d'outils et le plus vieil historique pour
tenir dans le contexte, et prévient si une réponse a quand même été coupée.
