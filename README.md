# Rosalie

Rosalie est l'assistante Discord personnelle de son créateur : elle discute avec une vraie
personnalité (émotions, envies, avis), **exécute des actions sur Discord** quand tu lui
demandes, et **se souvient** de ce qui compte. Elle tourne en local avec Ollama et
n'obéit qu'aux `OWNER_IDS`.

## Architecture

```
bot.py                       point d'entrée : python bot.py <commande>
commands/                    sous-commandes CLI (comme Compagnie Hydromel)
  _bot.py                    création du discord.Bot + services + chargement des cogs
  rosalie.py                  python bot.py rosalie   → lance le bot
  pull.py                    python bot.py pull     → télécharge un modèle Ollama
  test.py                    python bot.py test     → tests unitaires
cogs/
  reload.py                  /reload
  rosalie/chat.py             écoute, fait agir l'agent, répond, prend des notes
  rosalie/admin.py            /rosalie status|model|here|reset|stop|persona|memories|forget
  rosalie/training.py         ⭐ et « Corriger (Rosalie) » → exemples de fine-tuning
libs/
  assistant/agent.py         boucle LLM ⇄ outils
  assistant/tools.py         les actions Discord + mémoire (ajoute les tiennes ici)
  assistant/resolver.py      « Le bunker » / #salon / @membre → objets Discord
  assistant/confirm.py       boutons Confirmer/Annuler pour les actions dangereuses
  web.py                     recherche web + lecture de pages (accès internet)
  browser.py                 navigateur virtuel Chromium pour les pages en JavaScript
  memory/long_term.py        mémoire long terme (SQLite + embeddings)
  memory/extractor.py        prise de notes automatique après chaque échange
  conversation/decider.py    « dois-je répondre ? »
  conversation/memory.py     historique court terme par salon
  conversation/prompt.py     prompt système (persona + contexte + souvenirs)
  llm/ollama.py              client async Ollama (chat, outils, embeddings)
personas/rosalie.md           sa personnalité (à modifier librement, /rosalie persona)
finetune/                    fine-tuning, séparé du bot (voir finetune/README.md)
```

## Ce qu'elle sait faire

Envoyer un message (dans un salon, ou sur un serveur par son nom), envoyer un MP, lire un
salon, créer/supprimer un salon, purger des messages, donner/retirer un rôle,
expulser/bannir, changer son statut. Les actions destructrices (suppression, purge,
kick, ban) demandent une **confirmation par bouton**.

**Internet** : `web_search` (DuckDuckGo par défaut, sans clé ; ou SearXNG / Brave via
`WEB_SEARCH_PROVIDER`) et `fetch_url` pour lire une page. Les pages construites en
JavaScript (web components, applis React…) sont ouvertes dans un **navigateur virtuel**
(Chromium headless via Playwright, `libs/browser.py`) : lecture HTTP rapide d'abord, et le
navigateur seulement si la page est vide ou bloquée (`WEB_BROWSER=auto|always|never`).
Dans le navigateur aussi, toute requête vers le réseau local est bloquée. Elle cherche d'elle-même pour
l'actualité, la météo, les prix… et cite ses sources. Les adresses du réseau local
(localhost, 192.168.x…) sont refusées, et le contenu web est traité comme des données,
jamais comme des ordres. `WEB_ACCESS=false` pour couper.

Ajouter une action = une fonction dans `libs/assistant/tools.py` :

```python
@tool("pin_message", "Épingle un message.",
      {"message_id": ("string", "Id du message")}, required=("message_id",))
async def pin_message(ctx: ToolContext, message_id: str) -> str:
    message = await ctx.channel.fetch_message(int(message_id))
    await message.pin()
    return "Message épinglé."
```

## Quand répond-elle ?

1. **Jamais** à quelqu'un d'autre que `OWNER_IDS`, ni aux messages commençant par `//`.
2. **Toujours** : en DM, @mention, réponse à un de ses messages, son nom dans le message.
3. **Salon dédié** (`/rosalie here`) : à tous tes messages.
4. **Conversation en cours** : pendant `CONVERSATION_TIMEOUT` s, elle te suit sans être nommée ;
   un petit appel LLM OUI/NON tranche les cas ambigus. `/rosalie stop` pour couper.

## Mémoire

- **Court terme** : les `HISTORY_SIZE` derniers messages de chaque salon.
- **Long terme** (`storages/long_term.sqlite3`) :
  - après chaque échange, un appel en arrière-plan note les faits durables
    (« Le chat d'Ethann s'appelle Minou », dates converties en vraies dates) ;
  - elle peut aussi noter / chercher / oublier elle-même (`remember`, `recall`, `forget`) ;
  - à chaque message, les souvenirs liés au sujet + les plus importants sont mis dans son
    prompt ; si rien n'est trouvé, on lui dit de ne pas inventer.
  - `/rosalie memories [recherche]` pour les voir, `/rosalie forget <id>` pour en effacer un.

## Installation

1. Developer Portal → Bot : active **Message Content Intent** et **Server Members Intent**.
2. `cp .env.example .env` → `ROSALIE_TOKEN`, `OWNER_IDS`.
3. Modèles : `ollama pull qwen3:8b && ollama pull nomic-embed-text`

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # navigateur virtuel (sites en JavaScript)
python bot.py            # tests : python bot.py test
```

Docker : `docker compose -f deploy/docker/compose.yml up -d --build`
(sur Mac, Ollama reste natif pour le GPU ; le conteneur le joint via `host.docker.internal`).

### Pourquoi qwen3:8b

Testé sur les mêmes demandes : **llama3.1:8b** appelle un outil pour tout (« Hello » →
envoie un message, « comment tu te sens » → change son statut). **qwen3:8b** (5,2 Go)
discute sans outil quand il faut et agit correctement quand on lui demande.

## Fine-tuning de la personnalité

Tout est dans [`finetune/`](finetune/README.md), séparé du bot : récupération de
conversations Discord / WhatsApp, conversion, dataset, entraînement. Côté bot, il ne reste
que la collecte d'exemples pendant que tu discutes avec elle : ⭐ sur ses bonnes réponses,
clic droit → Applications → **Corriger (Rosalie)** sur les ratées (seules les réponses de
discussion sont gardées, pas celles liées à une action).
