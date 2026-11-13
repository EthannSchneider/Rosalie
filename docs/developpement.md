# Développement

Avant tout : [l'architecture](architecture.md). En résumé, le cœur (`libs/core/`) ne connaît
aucune messagerie ; les interfaces (`interfaces/`) traduisent ; les outils sont soit génériques
(`libs/assistant/tools/`), soit propres à une interface (`interfaces/<nom>/tools/`).

## Ajouter une interface

1. Crée `interfaces/<nom>/__init__.py` avec une sous-classe de
   [`Interface`](../libs/core/interface.py). L'interface terminal
   ([`interfaces/terminal/`](../interfaces/terminal/__init__.py)) est l'exemple minimal.
2. Enregistre-la dans [`interfaces/__init__.py`](../interfaces/__init__.py) (`AVAILABLE`).
3. C'est tout : `python bot.py` lance toutes les interfaces enregistrées sauf le terminal. Si
   la tienne ne peut pas démarrer (pas de token…), qu'elle le dise (`Log.warning`) et que
   `start()` se termine : les autres continuent.

Squelette (ex : Telegram) :

```python
from libs.core.interface import Interface
from libs.core.types import Conversation, Incoming, Person, Sent


class TelegramInterface(Interface):
    name = "telegram"          # préfixe des clés : « telegram:<id> »
    label = "Telegram"         # dans le prompt : « tu parles via Telegram »
    message_limit = 4096       # le cœur découpe les messages plus longs

    async def start(self):
        # Se connecter, puis pour chaque message reçu (hors bots) :
        #   await self.rosalie.receive(Incoming(conversation, author, text, message_id,
        #                                       mentioned=..., reply_to_bot=...))
        # et, si la messagerie le signale : self.rosalie.typing_from(conv.key, person.key)
        ...

    async def stop(self): ...

    async def send(self, conversation, text=None, *, files=(), reply_to=None) -> Sent: ...

    async def confirm(self, conversation, text, *, code=None, language=None):
        # Demander à l'owner (boutons, clavier…) ; renvoyer (accepté ?, Sent de la demande)
        ...

    async def conversation(self, conversation_id: str) -> Conversation | None: ...
    async def person(self, person_id: str) -> Person | None: ...
```

À savoir :

- `Person.is_owner` est décidé par l'interface (Discord : comptes liés à cet identifiant dont le rôle a au moins une permission `act.*`, `rosalie.discord_owners()` ; web : `user.has("act")` ; terminal : toujours).
  C'est la seule barrière entre « discuter » et « agir » : sois strict.
- `Conversation.private=True` pour un tête-à-tête : elle répond toujours.
- Facultatif : `typing()` (« écrit… »), `react()`, `prompt_context()` (lignes ajoutées au
  prompt), `destination()` (envoyer ailleurs que dans la conversation courante),
  `describe_error()` (traduire les exceptions de la messagerie pour le modèle).
- Ses outils propres : `interfaces/<nom>/tools/`, avec `@tool(..., requires="<nom>")`, importés
  quand l'interface est créée (voir `DiscordInterface.__init__`).

## Ajouter un outil

Générique (toutes interfaces) : une fonction dans le bon fichier de `libs/assistant/tools/`
(une nouvelle catégorie = un nouveau fichier, à importer dans `tools/__init__.py`).

```python
from libs.assistant.tools.base import ToolContext, ToolError, tool

@tool("roll_dice", "Lance un dé.", {"faces": ("integer", "Nombre de faces (défaut 6)")})
async def roll_dice(ctx: ToolContext, faces: int = 6) -> str:
    import random
    if faces < 2:
        raise ToolError("il faut au moins 2 faces")   # renvoyé tel quel au modèle
    return f"Résultat : {random.randint(1, faces)}"
```

Propre à Discord : dans `interfaces/discord/tools/`, avec `@discord_tool(...)` et les helpers
de `interfaces/discord/tools/helpers.py` (`client(ctx)`, `here(ctx)`, `_channel`, `_message`…).

Dans un outil, `ctx` donne : `ctx.rosalie` (services : `memory`, `long_term`, `agenda`,
`config`, `browser`, `send()`), `ctx.conversation`, `ctx.person`, `ctx.is_owner`,
`ctx.interface()`. Options de `@tool` : `confirm="Texte {param}"` (confirmation de l'owner
avant d'agir), `requires="<interface>"`. Les non-owners n'ont accès qu'à `GUEST_TOOLS`.

## Ajouter un réglage

Un `Field` dans [`libs/config/schema.py`](../libs/config/schema.py) + l'attribut dans `Config` :
page Réglages du site, `python bot.py settings` et validation suivent. Lis `rosalie.config.<clé>` au moment
de t'en servir (les réglages changent à chaud). Détails : [Réglages](reglages.md).

## Bases de données et migrations

Les bases `storages/config.sqlite3` et `storages/rosalie.sqlite3` passent par l'ORM SQLAlchemy
(`libs/db/`), et leur schéma par des migrations **Alembic** appliquées toutes seules à
l'ouverture (`Database(path, "main")`). Pour changer un modèle :

1. modifie la classe dans `libs/models/` (partagé par tout Rosalie, pas seulement le site) ;
2. génère la migration, puis **relis-la** :
   ```bash
   alembic -c migrations/alembic.ini --name main revision --autogenerate -m "ajoute X"
   alembic -c migrations/alembic.ini --name main check     # modèles == migrations ?
   ```
3. un test dans `tests/` (une base neuve, et une base de la version d'avant).

⚠️ **SQLite** : pour modifier une colonne, Alembic recrée la table (« batch ») à partir de la
base relue, et SQLAlchemy n'y relit ni `COLLATE NOCASE` ni `AUTOINCREMENT`. Pour ajouter une
colonne, préfère `op.add_column` (+ `op.create_index`) qui ne recrée rien — voir
`migrations/main/versions/0002_discord_id.py`.

`long_term.sqlite3` (souvenirs) reste pour l'instant en SQL direct (`libs/memory/long_term.py`).

## Le site web

Backend MVC dans `libs/webui/` (une route = une ligne dans `api/v1.py` + une méthode de
contrôleur + une vue), frontend React dans `webui/src/`. Détails : [Site web](site-web.md#architecture).

```bash
npm --prefix webui install
npm --prefix webui run dev     # http://localhost:5173, l'API vient de python bot.py (proxy /api)
npm --prefix webui run build   # -> webui/dist, servi par Python
```

## Tests

```bash
python bot.py test
```

`tests/helpers.py` fournit une interface factice (`FakeInterface`), une fausse interface
Discord, une Rosalie allégée et des contextes d'outils prêts à l'emploi (`make_ctx`,
`discord_ctx`). `tests/test_settings.py` couvre les réglages, la commande `settings` et l'API
du site ; `tests/test_web.py` les comptes, les rôles et le chat (vrai serveur sur un port libre,
Rosalie remplacée par un écho). Les tests n'écrivent pas dans `log.txt`.
