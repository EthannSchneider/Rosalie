# Réglages

Les réglages de Rosalie (token Discord, modèle, outils, personnalités, rythme…) ne sont
plus dans le `.env` : ils vivent dans **`storages/config.sqlite3`** (privé, ignoré par git) et se
modifient **à chaud**, sans redémarrer, de trois façons :

| Où | Comment |
|---|---|
| Site web | page *Réglages* de http://127.0.0.1:8765 (superadmin ; voir [Site web](site-web.md)) |
| Terminal | `python bot.py settings …` |
| Discord | `/rosalie model`, `/rosalie persona`, `/rosalie initiative`, `/rosalie here` |

Un changement est pris en compte au plus tard **une seconde** après, même s'il vient d'un autre
processus. Seuls quelques réglages (marqués *redémarrage* / `↻`) attendent le prochain lancement :
le token Discord, le modèle d'embeddings et la taille de l'historique.

Le `.env` ne garde que le démarrage : `STORAGE_DIR`, `LOG_FILE` et l'adresse du site
(`WEB_UI_HOST`, `WEB_UI_PORT`). Voir [`.env.example`](../.env.example).

## Migration depuis l'ancien `.env`

Au **premier lancement**, les anciennes variables (`INTERFACES`, `ROSALIE_TOKEN`, `OWNER_IDS`,
`OLLAMA_MODEL`, `DISABLED_TOOLS`, `PERSONA_FILE`…) sont importées dans la base, ainsi que le modèle et l'initiative
choisis sur Discord (`storages/settings.json`). Ensuite le `.env` n'est plus lu pour ces
réglages (`INTERFACES` et `WEB_UI` ne servent plus : `python bot.py` lance tout ; `OWNER_IDS` est
gardé de côté jusqu'à ce que tu lies ton compte à Discord, voir [Site web](site-web.md)) ; Rosalie signale au démarrage celles qui y traînent encore — tu peux les retirer.
`python bot.py settings import-env --force` réimporte le `.env` (écrase les valeurs actuelles).

## Page Réglages du site

Une page par groupe (Discord, Personnalité, Ollama, Conversation, Outils, Internet,
Exécution de code, Rythme, Heartbeat) et une page **Personas**. Les modifications s'accumulent
dans une barre *Enregistrer / Annuler* (`Ctrl/⌘+S`) ; *↺ défaut* revient à la valeur d'origine.

- **Outils** : cases à cocher (filtre, tout activer / désactiver) au lieu d'une liste à taper.
- **Secrets** (token, clé Brave) : jamais renvoyés au navigateur, seulement « défini / vide » ;
  taper une valeur la remplace, *Effacer* la vide.
- **Modèles** : suggestions tirées d'Ollama (`/api/tags`).

Accès réservé au superadmin (chaque compte a sa page *Mon compte*) ; sécurité du site : voir [Site web](site-web.md).

Le site est en React + React Router + Tailwind, construit avec Vite dans `webui/`
(organisation : [Site web → Architecture](site-web.md#architecture)) :

```bash
npm --prefix webui install
npm --prefix webui run build      # -> webui/dist, servi par Python
npm --prefix webui run dev        # développement : http://localhost:5173 (API : python bot.py)
```

Sans build, le site affiche comment le construire ; l'API et `python bot.py settings`
marchent quand même. L'image Docker le construit elle-même.

## En ligne de commande

```bash
python bot.py settings                        # tout (* = modifié, ↻ = au redémarrage)
python bot.py settings ollama                 # un groupe
python bot.py settings get num_ctx            # valeur, aide, défaut
python bot.py settings set num_ctx 32768      # l'ancien nom marche aussi : OLLAMA_NUM_CTX
python bot.py settings set channel_ids 123,456
python bot.py settings set discord_token      # secret : demandé sans écho
python bot.py settings reset num_ctx

python bot.py settings tools                  # ✓ activé, ⚠️ demande confirmation
python bot.py settings tools disable kick_member ban_member
python bot.py settings tools enable kick_member
```

## Personnalités

`rosalie` (le fichier [`personas/rosalie.md`](../personas/rosalie.md)) est la personnalité par
défaut, **intégrée et non modifiable** — comme tout fichier `personas/*.md` du dépôt. Les
tiennes sont des fichiers **`storages/personas/<nom>.md`** (privés, avec tes autres données ;
dans le volume en Docker). Crée-les, modifie-les, renomme-les depuis *Réglages → Personas* du
site, ou en ligne de commande — ou même directement dans le fichier : Rosalie reprend une
modification à chaud (au plus une seconde après). Nom de fichier : minuscules, chiffres, `-`
et `_`.

Les personnalités enregistrées en base par une version précédente sont exportées vers ces
fichiers au premier lancement (migration `config 0002`).

En ligne de commande :

```bash
python bot.py settings persona                       # liste (* = active)
python bot.py settings persona copy rosalie douce    # partir de Rosalie
python bot.py settings persona edit douce            # ouvre $EDITOR
python bot.py settings persona add pirate pirate.md  # depuis un fichier
python bot.py settings persona use douce             # l'activer (ou /rosalie persona douce)
python bot.py settings persona rename douce tendre
python bot.py settings persona delete tendre         # si active : retour à rosalie
```

## Ajouter un réglage (développement)

Un `Field` dans [`libs/config/schema.py`](../libs/config/schema.py) (type, défaut, groupe,
libellé, aide, `restart=` si besoin) + l'attribut du même nom dans `Config`
([`libs/config/__init__.py`](../libs/config/__init__.py)). La page Réglages du site, la commande
`settings` et la validation suivent automatiquement. Le code lit `rosalie.config.<clé>` (ou
`ctx.config` dans un outil) **au moment de s'en servir**, pas une copie gardée au démarrage.
