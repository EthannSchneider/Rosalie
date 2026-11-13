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
- Python 3.13, `py-cord` (import `discord`), `python-dotenv`, `playwright`, `SQLAlchemy` + `alembic`
  (bases de données). Pas d'autre dépendance sans raison : HTTP via `urllib` dans
  `asyncio.to_thread` (voir `libs/web.py`, `libs/llm/ollama.py`), serveur web en `http.server`.
- Site (`webui/`) : React, React Router, Tailwind, Vite — versions exactes dans `package.json`.
- **Bases de données** : ORM SQLAlchemy (`libs/db/`), schéma = migrations Alembic
  (`migrations/config`, `migrations/main`), appliquées à l'ouverture. Tout changement de modèle =
  une migration relue + `alembic … check` + un test. Jamais de `CREATE TABLE` à la main.
- Commits : messages en anglais style `feat: …` / `refactor: …`, sur `main`, poussés sur
  `origin` (github.com:EthannSchneider/Rosalie). Ne commite que si on te le demande.
- `.env` et `storages/` (mémoire, souvenirs, agenda, logs, **réglages** `config.sqlite3` avec le
  token Discord) sont privés et ignorés par git. Ne les
  affiche pas et n'envoie jamais leur contenu (ni l'e-mail de l'utilisateur) à un service externe.
  Tout nouveau réglage : un `Field` dans `libs/config/schema.py` + l'attribut dans `Config`
  (`libs/config/__init__.py`) + docs (`docs/reglages.md`). Le `.env` ne garde que le démarrage
  (`STORAGE_DIR`, `LOG_FILE`, `WEB_UI_HOST`, `WEB_UI_PORT`). `python bot.py` lance toutes les
  interfaces sauf le terminal (`interfaces.DEFAULT`) ; `python bot.py chat` le terminal seul.

## Commandes

```bash
python bot.py              # lance Rosalie : Discord + site web (toutes les interfaces sauf le terminal)
python bot.py chat         # terminal seulement — le moyen le plus simple de tester en vrai
python bot.py test         # tests unitaires (unittest, aucun réseau, n'écrivent pas log.txt)
python bot.py pull         # télécharge le modèle Ollama configuré
python bot.py settings     # voir / modifier les réglages (storages/config.sqlite3)
python bot.py web          # seulement le site, sans chat (http://127.0.0.1:8765)
python bot.py users        # comptes (add, passwd, role, discord, delete)
python bot.py roles        # rôles et permissions (add, set, label, delete)
npm --prefix webui run build   # construire le site (React, Vite) -> webui/dist
alembic -c migrations/alembic.ini --name main revision --autogenerate -m "…"   # nouvelle migration
python -m compileall -q libs interfaces commands
```

Pour un essai réel sans toucher aux données de l'utilisateur : `STORAGE_DIR` et `LOG_FILE` vers
un dossier temporaire, `WEB_UI_PORT` libre (pour arrêter une instance de test, vise son PID via
son port, jamais `pkill -f bot.py` : ça tuerait aussi la vraie), puis `python bot.py chat`. ⚠️ `load_dotenv()` lit
quand même le vrai `.env` : au premier lancement, ses anciens réglages (token compris) seraient
importés dans la base temporaire. Crée d'abord la base avec `store.set_meta("env_imported", "1")`
(voir `libs/config`), puis coupe le heartbeat : `python bot.py settings set heartbeat non`.

## Architecture (résumé)

```
bot.py → commands/            rosalie.py (run), chat.py (terminal), settings.py, web.py, test.py, pull.py
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
libs/config/                  Config, schema.py (chaque réglage), store.py (réglages SQLite +
                              personnalités : personas/*.md intégrées, storages/personas/*.md perso)
libs/db/                      Database (SQLite + SQLAlchemy), lance les migrations Alembic
libs/models/                  MODÈLES PARTAGÉS (ORM) : user, accounts, chat, config — utilisés par le
                              cœur, Discord, le site, les commandes ; ne dépendent pas de libs/webui
libs/webui/                   backend MVC du site : views/ (JSON) · controllers/ ·
                              api/v1.py (routes /api/v1 + droits) · router/http/security/events/server
interfaces/web/               WebInterface (chat : un compte = une conversation « web:<id> »)
migrations/                   Alembic : config/ (config.sqlite3), main/ (rosalie.sqlite3)
libs/llm/                     ollama.py (client), persona.py ; personas/*.md = intégrées (lecture seule)
webui/src/                    React : api/ · context/ · hooks/ · components/ · pages/ (Tailwind)
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
- **`Person.is_owner`** (décidé par l'interface ; Discord : comptes dont le rôle a `act`,
  liés à l'identifiant, `rosalie.discord_owners()` ; web : rôle du compte) est la seule barrière
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

- **Réglages à chaud** : `Rosalie.config` est une propriété qui relit `ConfigStore` (cache
  mémoire, `PRAGMA data_version` vérifié au plus une fois par seconde) et applique au client
  Ollama. Ne garde jamais une copie de la config au démarrage : lis `rosalie.config.x` au moment
  voulu (le décideur reçoit `lambda: self.config`). Les secrets ne sortent jamais vers le
  navigateur ni les logs (`Config.__repr__`, `display()` masquent).
- **Rôles et permissions** : un compte a un rôle (table `roles`), un rôle a des permissions
  (`PERMISSIONS` dans `libs/models/role.py` : chat, act, personas, settings, users, roles). Le code
  teste TOUJOURS `user.has("…")`, jamais un nom de rôle (sauf `superadmin`, verrouillé, qui a
  tout). `act` = owner (chat web et Discord via l'identifiant lié ; il n'y a plus d'`owner_ids`).
  Routes : `access="permission"` (ou tuple) dans `api/v1.py`. Anti-élévation :
  `controllers/guards.py` (on ne donne que ce qu'on a ; seul un superadmin touche un superadmin).
  Nouvelle permission = une entrée dans `PERMISSIONS` (+ docs) ; superadmin l'a d'office.
  Anciens `OWNER_IDS` gardés en méta (`legacy_owner_ids`), valables tant qu'aucun compte `act` n'est lié. Premier compte via le code d'installation de la
  console (ou `python bot.py users add`). Cookie HttpOnly SameSite=Strict, Origin vérifiée, JSON
  obligatoire pour écrire, Host local exigé en écoute locale, CSP stricte (pas d'`eval`).
- **API** : tout sous `/api/v1` ; une route = une ligne dans `libs/webui/api/v1.py` (méthode,
  chemin, accès public/user/settings/users) + une méthode de contrôleur + une vue. Les écritures
  exigent `Content-Type: application/json` (le client React l'envoie toujours).
- **Migrations SQLite** : le mode batch d'Alembic recrée la table et perd `COLLATE NOCASE` et
  `AUTOINCREMENT` ; pour ajouter une colonne, `op.add_column` + index (cf. 0002_discord_id).
- **Chat web** : le serveur HTTP tourne dans des fils ; tout appel au cœur repasse par la boucle
  asyncio (`run_coroutine_threadsafe` / `call_soon_threadsafe`). Événements vers le navigateur
  par `EventHub` (SSE). Rien de ce qui vient de Rosalie n'est inséré en HTML (Markdown.jsx rend
  des éléments React, jamais `dangerouslySetInnerHTML`).

## Ce qu'on a appris (pièges)

- **Le contexte est LA contrainte.** Prompt système + schémas des ~38 outils ≈ 5 000 tokens.
  Si `num_ctx` est trop petit, Ollama tronque lui-même le début et peut supprimer la question →
  HTTP 500 « no user query found in messages ». D'où : `OLLAMA_NUM_CTX=16384` par défaut,
  `fit_context` (raccourcit les gros résultats d'outils puis l'historique ancien, jamais le
  prompt système ni la dernière question), `result_budget(ctx)` (~40 % du contexte) pour les
  outils qui lisent beaucoup, `done_reason == "length"` signalé. Côté serveur Ollama,
  `OLLAMA_CONTEXT_LENGTH` doit aussi être assez grand. Chaque outil coûte ~100 tokens :
  le réglage `disabled_tools` (Réglages → Outils sur le site) pour en retirer.
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
  `interfaces/AVAILABLE` (lancée par défaut ; si elle ne peut pas démarrer, warning + fin de `start()`). Squelette dans `docs/developpement.md`.
- **Un outil** : fonction `@tool` dans le bon fichier de `libs/assistant/tools/` (ou
  `interfaces/discord/tools/` avec `@discord_tool`), un test dans `tests/`, une ligne dans
  `docs/fonctionnalites.md`.
- Toujours : `python bot.py test` vert avant de rendre la main. Rien n'est testé contre le vrai
  Discord automatiquement — dis-le quand c'est le cas.
