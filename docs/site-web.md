# Le site web : comptes et chat

L'interface **web** (`interfaces/web/`, active par défaut) lance avec Rosalie un site sur
**http://127.0.0.1:8765** :

| Page | Où | Permission | Quoi |
|---|---|---|---|
| **Chat** | onglet | `chat` | ta conversation privée avec Rosalie, en temps réel |
| **Mon compte** | menu de l'avatar | tout compte | ton rôle, ton identifiant Discord, ton mot de passe |
| **Réglages** | menu → *Administration* | `settings` (tout) ou `personas` (Personas seulement) | les réglages de Rosalie et ses personnalités ([détails](reglages.md)) |
| **Utilisateurs** | menu → *Administration* | `users` | créer des comptes, rôle, identifiant Discord, mot de passe, supprimer |
| **Rôles** | menu → *Administration* | `roles` | créer des rôles, choisir leurs permissions |

Le menu de l'avatar (en haut à droite) regroupe *Mon compte*, la section *Administration*
(les pages que ton rôle permet) et *Se déconnecter* ; son bouton affiche le nom de la page
ouverte. Sans la permission `chat`, l'accueil est *Mon compte*.

## Premier lancement : le superadmin

Tant qu'aucun compte n'existe, le site demande de créer le **superadmin**, avec un **code
d'installation** affiché dans la console de `python bot.py` (et dans `log.txt`) :

```
[WARNING] : Aucun compte sur le site : ouvre http://127.0.0.1:8765 et crée le superadmin avec le code d'installation 3F9A-C21E
```

Le code empêche le premier venu de prendre le compte. Il change à chaque lancement et ne sert
plus une fois le compte créé. Sans navigateur :
`python bot.py users add <nom> --role superadmin` (mot de passe demandé au clavier).

## Rôles et permissions

Chaque compte a **un rôle**, et un rôle est **une liste de permissions**. Les permissions sont
fixées par le code (c'est lui qui les vérifie) ; les rôles se gèrent sur la page **Rôles**
(permission `roles`) ou avec `python bot.py roles`.

| Permission | Ce qu'elle autorise |
|---|---|
| **Discussion** | |
| `chat` | utiliser le chat web |
| `web` | recherche web : chercher sur internet, lire une page, la météo (si l'accès internet est activé). Ne rend pas « owner » |
| **Faire agir Rosalie** | sur le site **et** sur Discord si l'identifiant Discord est lié : |
| `act.memory` | souvenirs : retenir, retrouver, oublier ; elle prend des notes et s'en sert dans la conversation |
| `act.followups` | relances et messages : `say`, programmer / annuler une relance |
| `act.images` | chercher et envoyer des photos |
| `act.discord_read` | Discord, lire : serveurs, salons, membres, rôles ; lire et chercher des messages |
| `act.discord_write` | Discord, écrire : envoyer (salon, DM), réagir, épingler, modifier, sondages, fils |
| `act.discord_manage` | Discord, gérer le serveur : salons, statut, invitations, purger / supprimer des messages |
| `act.discord_moderate` | Discord, modérer : rôles, expulser, bannir, exclure, surnoms |
| `act.code` | exécuter du code (toujours avec confirmation) |
| **Administration** | |
| `personas` | créer, modifier et choisir les personnalités |
| `settings` | tous les réglages de Rosalie |
| `users` | gérer les utilisateurs |
| `roles` | gérer les rôles |

Avec **au moins une** permission « Faire agir Rosalie », elle traite la personne comme son
créateur (conversation de créateur) ; elle ne lui propose et n'exécute que les outils que ces
permissions couvrent (table `libs/assistant/tools/permissions.py`). Sans aucune : invité, il
discute, et fait faire des recherches web s'il a `web`.

Les personnes **sans compte** (inconnus sur Discord) n'ont pas de rôle : elles discutent (si
*Discuter avec les autres* est activé) et ont la recherche web si le réglage Discord
**Recherche web pour les invités** (`guest_web`, activé par défaut) le permet.

Rôles de départ : **`superadmin`** (verrouillé : toujours toutes les permissions, même celles
ajoutées plus tard), **`admin`** (`chat`, `web` + toutes les `act.*`), **`user`** (`chat`, `web`). Les deux
derniers se modifient ; crée les tiens (ex : un « Modérateur » avec `act.discord_read` +
`act.discord_moderate`, un « Éditeur » avec seulement `personas`). Sur la page Rôles, « tout /
aucune » coche un groupe d'un coup.

Sur Discord, les commandes `/rosalie` demandent un compte lié avec au moins une permission
autre que `chat`, puis chacune la sienne : `model`, `initiative`, `/reload` → `settings` ;
`persona` → `personas` ; `memories`, `forget` → `act.memory` ; `agenda`, `cancel` →
`act.followups` ; ⭐ et *Corriger* → au moins une `act.*`.

Les migrations `main 0004` (l'ancienne permission `act` devient toutes les `act.*`) et `0005`
(`web` ajoutée à tous les rôles, puisqu'elle était ouverte à tous avant) gardent à chacun
exactement les mêmes droits.

Garde-fous contre l'élévation de droits :
- on ne peut donner un rôle — ou ajouter/retirer une permission à un rôle — que si on a soi-même
  toutes les permissions en jeu ;
- seul un superadmin peut nommer, modifier ou retirer un superadmin ; il en reste toujours au moins un ;
- un rôle encore attribué ne peut pas être supprimé ; on ne peut pas supprimer son propre compte.

Attention : `users` + `roles` ensemble permettent de se créer un rôle avec ce qu'on a, et de
l'attribuer — réserve ces deux permissions à des gens de confiance.

## Discord : à qui elle obéit

Il n'y a plus de liste d'owners : **chaque compte peut être lié à son identifiant Discord**
(*Mon compte*, la page *Utilisateurs*, ou `python bot.py users discord <nom> <id>`).
Sur Discord, Rosalie agit pour les comptes liés selon **les permissions `act.*` de leur rôle** :
outils, boutons de confirmation, ⭐. Sans aucune `act.*`, un compte lié reste un invité ; un
identifiant ne peut être lié qu'à un seul compte.

Identifiant Discord : clic droit sur ton profil → *Copier l'identifiant* (mode développeur :
Paramètres → Avancés).

**Transition depuis `OWNER_IDS`** : les anciens owners (du `.env` ou du réglage `owner_ids`)
sont gardés de côté (avec toutes les permissions) **tant qu'aucun compte avec une `act.*` n'est
lié** — Rosalie le signale au démarrage, et *Mon compte* propose de lier l'ancien identifiant
en un clic. Dès que c'est fait, ils sont ignorés.

Un compte sans `act.*` est soumis au réglage *Discuter avec les autres* (`public_replies`) et au
délai anti-spam, comme les invités Discord.

## Le chat

- Chaque compte a **sa propre conversation** (clé `web:<id>`) ; c'est la même Rosalie que sur
  Discord ou dans le terminal (mêmes souvenirs, même agenda). Si tu lui parles surtout sur le
  web, c'est là qu'elle t'écrira d'elle-même (initiative, relances).
- Les messages arrivent en direct (Server-Sent Events), avec « Rosalie écrit… ». Elle attend
  que tu aies fini d'écrire avant de répondre, comme ailleurs.
- Quand elle veut exécuter du code ou faire une action sensible, une **carte de confirmation**
  s'affiche avec *Exécuter / Confirmer* et *Annuler* (5 minutes pour répondre).
- Les photos qu'elle envoie s'affichent dans la conversation ; les autres fichiers se
  téléchargent. Ils sont stockés dans `storages/web_files/` et réservés à ton compte.
- *Effacer la conversation* vide l'historique affiché et sa mémoire courte de cette
  conversation ; ses souvenirs à long terme restent.
- Entrée pour envoyer, Maj+Entrée pour aller à la ligne.

`python bot.py web` lance le site **sans** Rosalie (réglages et comptes seulement, pas de chat).

## Comptes en ligne de commande

```bash
python bot.py users                           # liste
python bot.py users add lea                   # rôle user par défaut
python bot.py users add max --role admin --discord 123456789012345678
python bot.py users discord lea 223456789012345678   # « - » pour délier
python bot.py users passwd lea                # ferme aussi ses sessions
python bot.py users role lea admin
python bot.py users delete lea

python bot.py roles                             # rôles, permissions, nombre de comptes
python bot.py roles permissions                 # ce que permet chaque permission
python bot.py roles add editeur "Éditeur" personas
python bot.py roles set moderateur chat,act.discord_read,act.discord_moderate
python bot.py roles delete editeur              # seulement s'il n'est plus attribué
```

## Architecture

**Backend** (`libs/webui/`, bibliothèque standard), organisé en MVC. Les **modèles** ne sont pas
dans le site : ils vivent dans **`libs/models/`**, partagés avec le reste de Rosalie (le cœur s'en
sert pour savoir à qui obéir sur Discord, les commandes `users` aussi) :

| Dossier | Rôle |
|---|---|
| `libs/models/` | les données (ORM SQLAlchemy) : `Role` + `PERMISSIONS`, le dépôt `Roles` ; `User`, `LoginSession`, le dépôt `Accounts` ; `ChatMessage`, `ChatFile`, `ChatLog` ; `Setting`, `Meta` |
| `views/` | la forme des réponses JSON (seul endroit qui décide de ce qui sort : jamais de hash, jamais de secret) |
| `controllers/` | la logique par domaine : `session`, `account`, `settings`, `users`, `roles`, `chat` (+ `guards.py` : anti-élévation de droits) |
| `api/v1.py` | la table des routes `/api/v1/…`, avec le droit requis pour chacune |
| `router.py` · `http.py` · `security.py` · `events.py` · `server.py` | la plomberie : routage, requête/réponses, sécurité, temps réel, serveur HTTP |

L'API est **versionnée** : tout est sous `/api/v1`. Une version incompatible deviendra
`api/v2.py`, servie à côté de la v1 le temps que l'interface suive.

| Méthode | Route | Accès |
|---|---|---|
| GET | `/session` | public |
| POST | `/session/setup` · `/session/login` · `/session/logout` | public |
| PUT | `/account/password` · `/account/discord` | compte |
| GET | `/settings` | `settings` ou `personas` |
| PATCH | `/settings` ; GET `/settings/models` | `settings` |
| GET · PUT · DELETE | `/personas/{nom}` ; POST `/personas/{nom}/activate` · `/rename` | `personas` |
| GET | `/roles` (rôles + catalogue des permissions) | `roles` ou `users` |
| POST · PATCH · DELETE | `/roles` · `/roles/{nom}` | `roles` |
| GET · POST | `/users` ; PATCH · DELETE `/users/{id}` | `users` |
| GET · POST · DELETE | `/chat/messages` (DELETE = effacer la conversation) | `chat` |
| GET | `/chat/events` (Server-Sent Events) · `/chat/files/{id}` | `chat` |
| POST | `/chat/typing` · `/chat/confirmations/{id}` | `chat` |

**Bases de données** : `storages/rosalie.sqlite3` (comptes, sessions, chat ; anciennement
`web.sqlite3`, renommée automatiquement) et
`storages/config.sqlite3` (réglages), via l'ORM SQLAlchemy ; les personnalités personnalisées
sont des fichiers `storages/personas/*.md`. Leur schéma est tenu
par des **migrations Alembic** (`migrations/main/`, `migrations/config/`), appliquées
automatiquement à l'ouverture. Voir [Développement](developpement.md#bases-de-données-et-migrations).

**Frontend** (`webui/src/`, React + React Router + Tailwind, construit par Vite) :

| Dossier | Rôle |
|---|---|
| `api/` | client `/api/v1` + un module par domaine (session, account, settings, users, chat) |
| `context/` | session connectée, notifications, boîtes de dialogue |
| `hooks/` | `useChat` (historique + temps réel), `useSettings` (brouillon des réglages) |
| `components/` | `layout/` (en-tête, gardes de rôle), `ui/` (boutons, badges…), `chat/`, `settings/` |
| `pages/` | `auth/`, `chat/`, `account/`, `settings/` (une sous-route par groupe), `users/`, `roles/` |

Routes du navigateur : `/setup`, `/login`, `/chat`, `/account`, `/settings/<section>`, `/users`, `/roles`.
Le serveur renvoie `index.html` pour toute adresse qui n'est ni un fichier ni l'API.

## Sécurité

- Mots de passe hachés avec scrypt ; session par cookie `HttpOnly`, `SameSite=Strict`
  (30 jours). Après 5 mauvais mots de passe, attente croissante (jusqu'à 5 minutes).
- Changer un mot de passe ferme les autres sessions du compte ; supprimer un compte ferme
  toutes les siennes.
- Les requêtes venant d'un autre site sont refusées (Origin, `Sec-Fetch-Site`, JSON obligatoire
  pour écrire), et la CSP interdit tout script extérieur ou `eval` ; en écoute locale, l'en-tête Host doit être local (contre le DNS rebinding).
- Les secrets des réglages (token Discord, clé Brave) ne sont jamais envoyés au navigateur.
- Lier un identifiant Discord à un compte avec des `act.*` donne à cette personne Discord les droits de
  Rosalie : chaque compte ne peut lier que le sien (*Mon compte*) ; qui a `users` peut corriger
  les autres (*Utilisateurs*).
- Par défaut le site n'écoute que sur `127.0.0.1`. Pour l'ouvrir au réseau :
  `WEB_UI_HOST=0.0.0.0` dans le `.env` ; hors de chez toi, mets-le derrière un reverse proxy
  **HTTPS** (le site lui-même parle HTTP).
- Comptes, sessions et historique du chat : `storages/rosalie.sqlite3` (privé, ignoré par git).
