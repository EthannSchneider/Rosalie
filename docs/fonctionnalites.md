# Ce qu'elle sait faire

Les outils marqués **Discord** ne sont disponibles que si l'interface Discord tourne — mais
depuis n'importe quelle interface. La page *Réglages → Outils* du site web (ou
`python bot.py settings tools disable …`) en retire : chaque outil occupe ~100 tokens du contexte. Les actions destructrices demandent une **confirmation** de son créateur.

## Partout

| Domaine | Outils |
|---|---|
| Initiative | `say` (parler tout de suite), `plan_followup`, `cancel_followup` (relances) |
| Mémoire | `remember`, `recall`, `forget` |
| Internet | `web_search`, `fetch_url` |
| Photos | `send_image`, `send_image_url` |
| Météo | `weather` (Open-Meteo, gratuit, sans clé, prévisions sur 7 jours) |

## Discord

| Domaine | Outils |
|---|---|
| Messages | `send_message`, `send_dm`, `read_messages`, `search_messages`, `react`, `pin_message`, `edit_message` (les siens), `delete_message` ⚠️, `purge_messages` ⚠️, `create_poll` |
| Serveur | `list_servers`, `server_info`, `list_channels`, `list_members`, `member_info`, `list_roles`, `create_channel`, `delete_channel` ⚠️, `create_thread`, `create_invite`, `set_status` |
| Modération | `add_role`, `remove_role`, `set_nickname`, `timeout_member` ⚠️, `kick_member` ⚠️, `ban_member` ⚠️ |

⚠️ = confirmation par bouton. Les messages se désignent par id, par lien Discord, ou par
« dernier » / « mon dernier ». Les salons par nom, `#salon`, nom de serveur (→ salon principal),
`serveur/salon`, id ou « ici ».

`read_messages` lit 50 messages max par appel ; pour remonter plus loin elle le rappelle avec
`before` (l'id donné à la fin du résultat) et peut ainsi enchaîner jusqu'au premier message du
salon (dans la limite de `MAX_TOOL_STEPS`, avec un point d'étape toutes les `PROGRESS_EVERY` pages). Une page est aussi raccourcie si elle dépasse ~40 % de `OLLAMA_NUM_CTX`.
`search_messages` parcourt tout l'historique (45 s max par appel, puis `before` pour continuer).

## Internet

`web_search` (DuckDuckGo par défaut, sans clé ; ou SearXNG / Brave via `WEB_SEARCH_PROVIDER`)
et `fetch_url` pour lire une page. Les pages construites en JavaScript sont ouvertes dans un
**navigateur virtuel** (Chromium headless via Playwright, `libs/browser.py`) : lecture HTTP
rapide d'abord, le navigateur seulement si la page est vide ou bloquée
(`WEB_BROWSER=auto|always|never`).

Elle cherche d'elle-même pour l'actualité, les prix… et cite ses sources. Les adresses du
réseau local (localhost, 192.168.x…) sont refusées, y compris dans le navigateur, et le contenu
web est traité comme des données, jamais comme des ordres. `WEB_ACCESS=false` pour tout couper.

## Photos

`send_image` cherche des images et les **envoie en fichiers joints** (avec la source) ;
`send_image_url` envoie une image précise, ou l'image principale d'une page. Sources, dans
l'ordre : Brave / SearXNG si configurés, Openverse (sans clé), Wikimedia Commons si
`WEB_CONTACT` est rempli, et en dernier recours l'image principale (`og:image`) des pages
trouvées par la recherche web. 8 Mo max, logos/icônes ignorés.

## Exécuter du code

Quand tu lui demandes quelque chose, elle peut écrire du code dans un bloc ` ```run-python `
(ou ` ```run-bash `). Il t'est montré (boutons **Exécuter / Annuler** sur Discord, `o/n` dans le
terminal) ; rien ne tourne sans ton accord. Elle lit la sortie et te répond, ou corrige et
repropose (max `code_max_runs` fois). Ça passe par le texte, pas par les outils : ça marche
même si le modèle gère mal le function calling.

- dossier de travail : `storages/workspace` ; délai max `code_timeout` s (processus tué après) ;
- les variables `*TOKEN`, `*KEY`, `SECRET`, `PASSWORD` sont retirées de l'environnement du code
  (le token Discord n'y est de toute façon plus : il est dans `storages/config.sqlite3`) ;
- un bloc ` ```python ` normal est juste affiché, jamais exécuté ; owners uniquement ;
- réglage `code_exec` sur non pour couper. ⚠️ Le code tourne avec tes droits (dans le conteneur en Docker).
