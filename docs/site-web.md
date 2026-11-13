# Le site web : comptes et chat

L'interface **web** (`interfaces/web/`, active par défaut) lance avec Rosalie un site sur
**http://127.0.0.1:8765** :

| Page | Où | Qui | Quoi |
|---|---|---|---|
| **Chat** | onglet | tout compte | ta conversation privée avec Rosalie, en temps réel |
| **Mon compte** | menu de l'avatar | tout compte | ton identifiant Discord, ton mot de passe |
| **Réglages** | menu de l'avatar → *Superadmin* | superadmin | les réglages de Rosalie et ses personnalités ([détails](reglages.md)) |
| **Utilisateurs** | menu de l'avatar → *Superadmin* | superadmin | créer des comptes, rôle, identifiant Discord, mot de passe, supprimer |

Le menu de l'avatar (en haut à droite) regroupe *Mon compte*, la section *Superadmin* (si tu
l'es) et *Se déconnecter* ; son bouton affiche le nom de la page ouverte.

## Premier lancement : le superadmin

Tant qu'aucun compte n'existe, le site demande de créer le **superadmin**, avec un **code
d'installation** affiché dans la console de `python bot.py` (et dans `log.txt`) :

```
[WARNING] : Aucun compte sur le site : ouvre http://127.0.0.1:8765 et crée le superadmin avec le code d'installation 3F9A-C21E
```

Le code empêche le premier venu de prendre le compte. Il change à chaque lancement et ne sert
plus une fois le compte créé. Sans navigateur :
`python bot.py users add <nom> --role superadmin` (mot de passe demandé au clavier).

## Rôles

| Rôle | Réglages, comptes | Chat web et Discord (si lié) |
|---|---|---|
| `superadmin` | ✓ | son créateur : outils, souvenirs, code (avec confirmation) |
| `admin` | — | son créateur : outils, souvenirs, code (avec confirmation) |
| `user` | — | invité : discussion et recherche seulement |

## Discord : à qui elle obéit

Il n'y a plus de liste d'owners : **chaque compte peut être lié à son identifiant Discord**
(*Mon compte*, la page *Utilisateurs* du superadmin, ou `python bot.py users discord <nom> <id>`).
Sur Discord, Rosalie obéit aux comptes **admin et superadmin liés** : commandes `/rosalie`,
actions, boutons de confirmation, ⭐. Un compte `user` lié reste un invité ; un identifiant ne
peut être lié qu'à un seul compte.

Identifiant Discord : clic droit sur ton profil → *Copier l'identifiant* (mode développeur :
Paramètres → Avancés).

**Transition depuis `OWNER_IDS`** : les anciens owners (du `.env` ou du réglage `owner_ids`)
sont gardés de côté et restent valables **tant qu'aucun compte admin n'est lié** — Rosalie le
signale au démarrage, et *Mon compte* propose au superadmin de lier l'ancien identifiant en un
clic. Dès qu'un compte admin est lié, ils sont ignorés.

Il reste toujours au moins un superadmin : le dernier ne peut être ni supprimé ni rétrogradé.
Un compte `user` est soumis au réglage *Discuter avec les autres* (`public_replies`) et au
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
```

## Architecture

**Backend** (`libs/webui/`, bibliothèque standard), organisé en MVC. Les **modèles** ne sont pas
dans le site : ils vivent dans **`libs/models/`**, partagés avec le reste de Rosalie (le cœur s'en
sert pour savoir à qui obéir sur Discord, les commandes `users` aussi) :

| Dossier | Rôle |
|---|---|
| `libs/models/` | les données (ORM SQLAlchemy) : `User`, `LoginSession`, le dépôt `Accounts` ; `ChatMessage`, `ChatFile`, `ChatLog` ; `Setting`, `Meta` |
| `views/` | la forme des réponses JSON (seul endroit qui décide de ce qui sort : jamais de hash, jamais de secret) |
| `controllers/` | la logique par domaine : `session`, `account`, `settings`, `users`, `chat` |
| `api/v1.py` | la table des routes `/api/v1/…`, avec le droit requis pour chacune |
| `router.py` · `http.py` · `security.py` · `events.py` · `server.py` | la plomberie : routage, requête/réponses, sécurité, temps réel, serveur HTTP |

L'API est **versionnée** : tout est sous `/api/v1`. Une version incompatible deviendra
`api/v2.py`, servie à côté de la v1 le temps que l'interface suive.

| Méthode | Route | Accès |
|---|---|---|
| GET | `/session` | public |
| POST | `/session/setup` · `/session/login` · `/session/logout` | public |
| PUT | `/account/password` · `/account/discord` | compte |
| GET · PATCH | `/settings` ; GET `/settings/models` | superadmin |
| GET · PUT · DELETE | `/personas/{nom}` ; POST `/personas/{nom}/rename` | superadmin |
| GET · POST | `/users` ; PATCH · DELETE `/users/{id}` | superadmin |
| GET · POST · DELETE | `/chat/messages` (DELETE = effacer la conversation) | compte |
| GET | `/chat/events` (Server-Sent Events) · `/chat/files/{id}` | compte |
| POST | `/chat/typing` · `/chat/confirmations/{id}` | compte |

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
| `pages/` | `auth/`, `chat/`, `account/`, `settings/` (une sous-route par groupe), `users/` |

Routes du navigateur : `/setup`, `/login`, `/chat`, `/account`, `/settings/<section>`, `/users`.
Le serveur renvoie `index.html` pour toute adresse qui n'est ni un fichier ni l'API.

## Sécurité

- Mots de passe hachés avec scrypt ; session par cookie `HttpOnly`, `SameSite=Strict`
  (30 jours). Après 5 mauvais mots de passe, attente croissante (jusqu'à 5 minutes).
- Changer un mot de passe ferme les autres sessions du compte ; supprimer un compte ferme
  toutes les siennes.
- Les requêtes venant d'un autre site sont refusées (Origin, `Sec-Fetch-Site`, JSON obligatoire
  pour écrire), et la CSP interdit tout script extérieur ou `eval` ; en écoute locale, l'en-tête Host doit être local (contre le DNS rebinding).
- Les secrets des réglages (token Discord, clé Brave) ne sont jamais envoyés au navigateur.
- Lier un identifiant Discord à un compte admin donne à cette personne Discord les droits de
  Rosalie : chaque compte ne peut lier que le sien (*Mon compte*) ; le superadmin peut corriger
  n'importe lequel (*Utilisateurs*).
- Par défaut le site n'écoute que sur `127.0.0.1`. Pour l'ouvrir au réseau :
  `WEB_UI_HOST=0.0.0.0` dans le `.env` ; hors de chez toi, mets-le derrière un reverse proxy
  **HTTPS** (le site lui-même parle HTTP).
- Comptes, sessions et historique du chat : `storages/rosalie.sqlite3` (privé, ignoré par git).
