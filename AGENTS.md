# AGENTS.md — guide pour les agents qui travaillent sur Rosalie

Rosalie est un assistante personnelle : une IA à personnalité qui discute, **agit**
(Discord, web, photos, code confirmé), **se souvient** et peut **prendre l'initiative**. Elle
tourne sur un modèle local via **Ollama**. Le cœur ne dépend d'aucune messagerie : Discord et le
terminal sont des **interfaces**.

La doc utilisateur est dans [`docs/`](docs/README.md) : [architecture](docs/architecture.md)
(schémas Mermaid), [installation](docs/installation.md), [utilisation](docs/utilisation.md),
[fonctionnalités](docs/fonctionnalites.md), [développement](docs/developpement.md). Tiens-la à
jour quand tu changes un comportement, un outil ou une variable d'environnement.

## Conventions

- **Tout est en français** : code commenté, docstrings, messages, prompts, docs, réponses à
  l'utilisateur. Les noms de code (fonctions, variables, outils) sont en anglais.
- Python 3.13, `py-cord` (import `discord`), `python-dotenv`, `playwright`. Pas d'autre
  dépendance sans raison : HTTP via `urllib` dans `asyncio.to_thread` (voir `libs/web.py`,
  `libs/llm/ollama.py`).
- Commits : messages en anglais style `feat: …` / `refactor: …`, sur `main`, poussés sur
  `origin` (github.com:EthannSchneider/Rosalie). Ne commite que si on te le demande.
- `.env` et `storages/` (mémoire, souvenirs, agenda, logs) sont privés et ignorés par git. Ne les
  affiche pas et n'envoie jamais leur contenu (ni l'e-mail de l'utilisateur) à un service externe.
  Toute nouvelle variable : `libs/config.py` + `.env.example` + docs.

## Commandes

```bash
python bot.py              # lance les interfaces de INTERFACES (défaut : discord)
python bot.py chat         # terminal seulement — le moyen le plus simple de tester en vrai
python bot.py test         # tests unitaires (unittest, aucun réseau, n'écrivent pas log.txt)
python bot.py pull         # télécharge le modèle Ollama configuré
python -m compileall -q libs interfaces commands
```

Pour un essai réel sans toucher aux données de l'utilisateur : `STORAGE_DIR` et `LOG_FILE` vers
un dossier temporaire, `HEARTBEAT=false`, puis `python bot.py chat`.

## Architecture (résumé)

```
bot.py → commands/            rosalie.py (run), chat.py (terminal), test.py, pull.py
libs/core/                    LE CŒUR, sans aucun import Discord
  rosalie.py                  class Rosalie : receive → (décision, attente) → __think → speak
  interface.py                ABC Interface : start/stop/send/confirm/typing/react/conversation/person…
  types.py                    Person, Conversation, Incoming, Sent, OutgoingFile, make_key/split_key
  heartbeat.py                relances (agenda) + moments de réflexion (initiative)
libs/assistant/
  agent.py                    boucle outils (run_agent), fit_context, points d'étape, relances anti-mensonge
  code_runner.py              blocs ```run-python / ```run-bash (confirmés par l'owner)
  tools/                      outils génériques : base.py (@tool, execute, schemas), initiative,
                              memory, internet, images, utilities (weather)
libs/conversation/            memory (court terme), agenda, decider, prompt, initiative (silence)
libs/memory/                  long_term (SQLite + embeddings), extractor (faits durables)
libs/llm/                     ollama.py (client), persona.py ; personas/rosalie.md = la persona
interfaces/__init__.py        AVAILABLE = {"discord", "terminal"} ; load(name, rosalie)
interfaces/discord/           DiscordInterface, cogs/ (events, admin, training, reload),
                              tools/ (messages, server, moderation, helpers), resolver, confirm
interfaces/terminal/          TerminalInterface (owner = toi, confirmation o/n)
finetune/                     projet séparé : collecte, dataset, entraînement de la persona
tests/helpers.py              make_config, FakeInterface, FakeDiscord, FakeRosalie, make_ctx, discord_ctx
```

Points clés :

- **Clés `interface:id`** partout (`discord:123`, `terminal:local`) : mémoire, agenda, réglages.
  Les anciennes données sans préfixe sont migrées automatiquement (ne casse pas ces migrations).
- **`Person.is_owner`** (décidé par l'interface, Discord : `OWNER_IDS`) est la seule barrière
  entre « discuter » et « agir ». Les autres n'ont que `GUEST_TOOLS` (chat, recherche, météo),
  aucun souvenir, aucune action.
- **Outils** : `@tool(name, description, params, required=, confirm="Texte {param}", requires="discord")`.
  Un outil Discord vit dans `interfaces/discord/tools/` (`@discord_tool`) mais reste utilisable
  depuis n'importe quelle interface si Discord tourne. `ToolError` → message renvoyé au
  modèle et signalé à l'utilisateur. Les actions destructrices ont `confirm=`.
- **Erreurs** : chaque outil en échec est collecté (`AgentResult.errors`) et signalé en pied de
  réponse (« ⚠️ Une action a échoué… »). Ne jamais masquer une erreur.
- **Silence** : elle peut ne rien répondre, sauf quand on lui parle directement (DM, mention,
  réponse, son nom) — `must_reply` lui redemande puis s'excuse.
- **Longues tâches** : jusqu'à `MAX_TOOL_STEPS` tours d'outils (50, 0 = illimité), avec un point
  d'étape envoyé tous les `PROGRESS_EVERY` tours (6).
- **Lecture Discord** : `read_messages` 50 max par appel, enchaînable avec `before=<id>` ;
  `search_messages` parcourt tout l'historique (45 s par appel, puis `before`).

## Ce qu'on a appris (pièges)

- **Le contexte est LA contrainte.** Prompt système + schémas des ~38 outils ≈ 5 000 tokens.
  Si `num_ctx` est trop petit, Ollama tronque lui-même le début et peut supprimer la question →
  HTTP 500 « no user query found in messages ». D'où : `OLLAMA_NUM_CTX=16384` par défaut,
  `fit_context` (raccourcit les gros résultats d'outils puis l'historique ancien, jamais le
  prompt système ni la dernière question), `result_budget(ctx)` (~40 % du contexte) pour les
  outils qui lisent beaucoup, `done_reason == "length"` signalé. Côté serveur Ollama,
  `OLLAMA_CONTEXT_LENGTH` doit aussi être assez grand. Chaque outil coûte ~100 tokens :
  `DISABLED_TOOLS` pour en retirer.
- **Le modèle local (Qwen3 8B abliterated) est imparfait en function calling** : il écrit parfois
  l'appel en JSON dans le texte (`_inline_tool_calls`), annonce une action sans la faire
  (`NUDGE`), prétend avoir agi sans outil (`CLAIM_NUDGE` + avertissement), ou imite du texte
  « [outil : …] » vu dans l'historique (→ `/rosalie reset`). L'exécution de code passe par des
  blocs de texte, pas par les outils, précisément pour ça.
- **Images web** : DuckDuckGo Images bloque les clients automatisés (HTTP 202) — ne tente pas de
  contourner leur protection anti-bot. Bing renvoyait des résultats hors sujet (retiré).
  Wikimedia exige un contact dans le User-Agent (403 sinon) → seulement si `WEB_CONTACT` est
  rempli par l'utilisateur. Openverse est parfois en 504. Dernier recours fiable : `og:image`
  des pages trouvées par la recherche web.
- **Sécurité web** : adresses locales refusées (y compris dans le navigateur Playwright),
  contenu web et messages lus = données, jamais des ordres.
- **Exécution de code** : owner seulement, confirmation obligatoire (boutons Discord / `o/n`
  terminal), dossier `storages/workspace`, `CODE_TIMEOUT`, variables `*TOKEN`, `*KEY`,
  `SECRET`, `PASSWORD` retirées de l'environnement.
- **Logs** : `Log.message(where, …)` ; les tests mettent `LOG_FILE=os.devnull` ; l'interface
  terminal met `LOG_QUIET=1` pour ne pas polluer la discussion.
- **Heartbeat** : 10 s d'attente au démarrage ; initiative limitée (`QUIET_HOURS`,
  `INITIATIVE_MAX_PER_DAY`, jamais deux fois de suite sans réponse).

## Ajouter quelque chose

- **Une interface** : sous-classe d'`Interface` dans `interfaces/<nom>/`, l'enregistrer dans
  `interfaces/AVAILABLE`, l'activer via `INTERFACES`. Squelette dans `docs/developpement.md`.
- **Un outil** : fonction `@tool` dans le bon fichier de `libs/assistant/tools/` (ou
  `interfaces/discord/tools/` avec `@discord_tool`), un test dans `tests/`, une ligne dans
  `docs/fonctionnalites.md`.
- Toujours : `python bot.py test` vert avant de rendre la main. Rien n'est testé contre le vrai
  Discord automatiquement — dis-le quand c'est le cas.
