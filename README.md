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
  rosalie/heartbeat.py        ❤️ battement régulier : relances programmées + initiative
  rosalie/training.py         ⭐ et « Corriger (Rosalie) » → exemples de fine-tuning
libs/
  assistant/agent.py         boucle LLM ⇄ outils
  assistant/tools/           les outils, un fichier par catégorie (ajoute les tiens ici) :
    base.py                  socle : ToolContext, @tool, registre, exécution sécurisée
    server.py                serveurs, salons, membres, statut
    messages.py              envoyer / lire / purger des messages
    moderation.py            rôles, kick, ban
    initiative.py            say, relances programmées
    memory.py                souvenirs à long terme
    internet.py              recherche web, lecture de pages
    images.py                chercher et envoyer des photos
  assistant/resolver.py      « Le bunker » / #salon / @membre → objets Discord
  assistant/confirm.py       boutons Confirmer/Annuler (actions dangereuses, code à exécuter)
  assistant/code_runner.py   exécution du code qu'elle écrit (```run-python / ```run-bash)
  web.py                     recherche web + lecture de pages (accès internet)
  browser.py                 navigateur virtuel Chromium pour les pages en JavaScript
  memory/long_term.py        mémoire long terme (SQLite + embeddings)
  memory/extractor.py        prise de notes automatique après chaque échange
  conversation/decider.py    « dois-je répondre ? »
  conversation/agenda.py     relances programmées + état de l'initiative (storages/agenda.json)
  conversation/initiative.py silence, heures calmes, « puis-je écrire d'elle-même ? »
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
Dans le navigateur aussi, toute requête vers le réseau local est bloquée.

**Photos** : `send_image` cherche des images et les **envoie en fichiers joints** sur Discord
(avec la source) ; `send_image_url` envoie une image précise ou l'image principale d'une page.
Sources : Brave / SearXNG si configurés (`WEB_SEARCH_PROVIDER`), puis Openverse (sans clé),
Wikimedia Commons si `WEB_CONTACT` est rempli, et en dernier recours l'image principale
(`og:image`) des pages trouvées par la recherche web. Réseau local refusé, 8 Mo max,
logos/icônes ignorés. Elle cherche d'elle-même pour
l'actualité, la météo, les prix… et cite ses sources. Les adresses du réseau local
(localhost, 192.168.x…) sont refusées, et le contenu web est traité comme des données,
jamais comme des ordres. `WEB_ACCESS=false` pour couper.

Ajouter une action = une fonction dans le bon fichier de `libs/assistant/tools/` (une nouvelle catégorie = un nouveau fichier, à importer dans `tools/__init__.py`) :

```python
from libs.assistant.tools.base import ToolContext, tool

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

## Exécuter du code

Quand tu lui demandes quelque chose, elle peut écrire du code dans un bloc ` ```run-python `
(ou ` ```run-bash `). Le bot t'envoie ce code sur Discord avec **Exécuter / Annuler** ; rien ne
tourne sans ton clic. La sortie s'affiche sous le code, elle la lit et te répond (ou corrige et
repropose, max `CODE_MAX_RUNS` fois). Ça passe par le texte, pas par les outils : ça marche
même si le modèle gère mal le function calling.

- dossier de travail : `storages/workspace` ; délai max `CODE_TIMEOUT` s (processus tué après) ;
- les tokens / clés du `.env` sont retirés de l'environnement du code ;
- un bloc ` ```python ` normal est juste affiché, jamais exécuté ; owners uniquement ;
- `CODE_EXEC=false` pour couper. ⚠️ Le code tourne avec tes droits (dans le conteneur en Docker).

## Plus qu'un répondeur : initiative et heartbeat

- **Elle attend que tu aies fini** : après ton message, elle patiente `REPLY_DELAY` s (plus
  longtemps si tu es en train d'écrire, max `REPLY_MAX_WAIT` s) et répond à l'ensemble.
- **Elle peut se taire** : si ton message n'appelle pas de réponse, elle répond `[SILENCE]` et
  rien n'est envoyé (un ✅ si elle a quand même agi).
- **Elle peut parler en plusieurs temps** : outil `say` → « je regarde ça » tout de suite,
  puis le résultat quand elle a fini.
- **Elle peut revenir plus tard** : outil `plan_followup` (rappel, prendre des nouvelles,
  relancer, réponse plus réfléchie). Au moment venu, elle décide encore si c'est utile.
  `/rosalie agenda`, `/rosalie cancel <id>`.
- **Heartbeat** (`HEARTBEAT_INTERVAL`, 60 s) : déclenche les relances, et toutes les
  `INITIATIVE_EVERY` min, si vous n'avez pas parlé depuis `INITIATIVE_MIN_SILENCE` min,
  elle a un *moment de réflexion* dans ta dernière conversation : elle t'écrit d'elle-même
  si elle a une vraie raison, sinon silence. Jamais pendant `QUIET_HOURS`, max
  `INITIATIVE_MAX_PER_DAY` par jour, et jamais deux fois de suite sans réponse de ta part.
  `/rosalie initiative false` pour couper.

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
