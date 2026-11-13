# Architecture

Rosalie est découpée en trois couches :

- **Les interfaces** (`interfaces/`) : par où on lui parle (Discord, terminal…). Elles ne font
  que traduire : message reçu → `Incoming`, réponse du cœur → message de la messagerie.
- **Le cœur** (`libs/core/`) : *qui* elle est et *comment* elle converse — décider de répondre,
  attendre que tu aies fini d'écrire, réfléchir avec ses outils, faire confirmer du code,
  se taire, revenir plus tard. Il ne connaît aucune messagerie, seulement le contrat
  [`Interface`](../libs/core/interface.py).
- **Les services** (`libs/`) : le modèle (Ollama), les mémoires, l'agenda, internet,
  l'exécution de code, les outils génériques.

## Vue d'ensemble

```mermaid
flowchart TB
    subgraph EXT["Messageries"]
        DSC(["Discord"])
        TTY(["Terminal"])
        NEW(["… ta prochaine interface"])
    end

    subgraph IFACES["interfaces/ — traduction"]
        DI["discord/<br/>DiscordInterface<br/>cogs : events · admin · training · reload<br/>outils Discord : server · messages · moderation"]
        TI["terminal/<br/>TerminalInterface"]
        NI["&lt;nom&gt;/<br/>sous-classe d'Interface"]
    end

    subgraph CORE["libs/core/ — le cœur"]
        ROS["rosalie.py — Rosalie<br/>receive · speak · send"]
        HB["heartbeat.py<br/>relances + initiative"]
        CONTRACT["interface.py — contrat Interface<br/>types.py — Person · Conversation · Incoming"]
    end

    subgraph SERVICES["libs/ — services"]
        DEC["conversation/decider.py<br/>dois-je répondre ?"]
        AG["assistant/agent.py<br/>boucle modèle ⇄ outils"]
        TOOLS["assistant/tools/<br/>outils génériques"]
        CODE["assistant/code_runner.py<br/>code confirmé puis exécuté"]
        MEM["conversation/memory.py — court terme<br/>memory/long_term.py — souvenirs"]
        AGD["conversation/agenda.py<br/>relances programmées"]
        PR["conversation/prompt.py<br/>persona + contexte + souvenirs"]
        LLM["llm/ollama.py"]
        WEB["web.py · browser.py"]
    end

    OLL[("Ollama")]
    NET[("Internet")]
    DISK[("storages/<br/>mémoire · souvenirs · agenda · réglages")]

    DSC <--> DI
    TTY <--> TI
    NEW <-.-> NI
    DI -- "Incoming" --> ROS
    TI -- "Incoming" --> ROS
    NI -. "Incoming" .-> ROS
    ROS -- "send · typing · confirm" --> DI
    ROS -- "send · confirm" --> TI
    DI -. "implémente" .-> CONTRACT
    TI -. "implémente" .-> CONTRACT
    HB --> ROS
    ROS --> DEC
    ROS --> PR
    ROS --> AG
    ROS --> CODE
    AG --> TOOLS
    AG --> LLM
    TOOLS --> MEM
    TOOLS --> AGD
    TOOLS --> WEB
    DI -. "outils requires=discord" .-> TOOLS
    HB --> AGD
    LLM --> OLL
    WEB --> NET
    MEM --> DISK
    AGD --> DISK
```

## Le trajet d'un message

```mermaid
sequenceDiagram
    autonumber
    actor U as Toi
    participant I as Interface<br/>(Discord, terminal…)
    participant R as Rosalie<br/>(libs/core/rosalie.py)
    participant D as ReplyDecider
    participant A as Agent + outils
    participant O as Ollama

    U->>I: message
    I->>R: receive(Incoming)
    R->>D: decide(incoming, historique)
    D-->>R: répondre ? direct ? garder en mémoire ?
    Note over R: attend que tu aies fini d'écrire<br/>(REPLY_DELAY, prolongé par « écrit… »)
    R->>I: typing()
    R->>A: run_agent(prompt + historique)
    loop jusqu'à une réponse finale
        A->>O: chat (avec les outils disponibles)
        O-->>A: texte ou appels d'outils
        A->>A: execute(outil) — confirmation via l'interface si dangereux
    end
    A-->>R: réponse, trace, erreurs
    opt bloc run-python / run-bash dans la réponse
        R->>I: confirm(code)
        I->>U: Exécuter / Annuler
        U-->>I: Exécuter
        R->>R: run_code → sortie renvoyée au modèle
    end
    alt [SILENCE] (et on ne lui parlait pas directement)
        R-->>I: rien (✅ si elle a agi)
    else réponse
        R->>I: send(réponse + erreurs éventuelles)
        I->>U: message
    end
    R->>R: mémoire court terme + prise de notes (souvenirs)
```

Le **heartbeat** suit le même chemin sans message entrant : à chaque battement, il retrouve la
conversation d'une relance (ou la dernière conversation avec toi) par sa clé, et appelle
`speak()` avec une consigne (« c'est le moment de ta relance… », « moment de réflexion… »).

## Identifier une conversation ou une personne

Tout ce qui est persistant (historique, agenda, conversations dédiées, conversations actives)
utilise une **clé `interface:id`** : `discord:1139156385280573530`, `terminal:local`…
Le cœur ne manipule que ces clés et les types de [`libs/core/types.py`](../libs/core/types.py) :

| Type | Rôle |
|---|---|
| `Person` | qui parle : id natif, noms, `is_owner` (calculé par l'interface) |
| `Conversation` | où l'on parle : id natif, description (`place`), tête-à-tête ou non, objet natif |
| `Incoming` | un message reçu + les signaux calculés par l'interface (mention, réponse…) |
| `Sent` / `OutgoingFile` | un message envoyé / un fichier à envoyer |

Les fichiers d'avant la restructuration (ids Discord bruts) sont repris automatiquement.

## Les outils

- **Génériques** (`libs/assistant/tools/`) : `say`, relances, souvenirs, recherche web,
  lecture de pages, photos, météo. Ils marchent quelle que soit l'interface.
- **Propres à une interface** (`interfaces/<nom>/tools/`) : déclarés avec
  `@tool(..., requires="<nom>")`. Ils ne sont proposés au modèle que si l'interface tourne —
  mais depuis **n'importe quelle** interface : depuis le terminal, elle peut écrire sur Discord.

## Arborescence

```
bot.py                         point d'entrée : python bot.py <commande>
commands/                      rosalie (défaut) · chat · settings · users · web · pull · test
interfaces/
  __init__.py                  registre des interfaces (python bot.py : toutes sauf le terminal)
  discord/
    __init__.py                DiscordInterface : Discord ⇄ cœur
    cogs/                      events (messages, « écrit… ») · admin (/rosalie) · training (⭐) · reload
    tools/                     outils Discord : server · messages · moderation (+ helpers)
    resolver.py                « Le bunker » / #salon / @membre → objets Discord
    confirm.py                 boutons Confirmer/Annuler, Exécuter/Annuler
    utils.py                   description d'un salon, texte lisible d'un message
  terminal/__init__.py         TerminalInterface : discuter dans la console
  web/__init__.py              WebInterface : le lien entre le site et le cœur (un compte = une conversation)
libs/
  core/                        le cœur : rosalie.py · heartbeat.py · interface.py · types.py · text.py
  assistant/                   agent.py · code_runner.py · tools/ (génériques)
  conversation/                decider · memory · prompt · agenda · initiative
  memory/                      long_term (SQLite + embeddings) · extractor (prise de notes)
  llm/                         ollama · persona
  web.py · browser.py          internet, navigateur virtuel
  db/                          Database : SQLite + ORM SQLAlchemy, migrations Alembic appliquées à l'ouverture
  config/                      Config · schema (chaque réglage) · models (ORM) · store (config.sqlite3 + storages/personas/*.md)
  models/                      modèles de données partagés (ORM) : user · accounts · chat · config
  webui/                       backend MVC du site : views/ · controllers/ · api/v1.py · server.py
  settings.py · log.py
personas/rosalie.md            sa personnalité par défaut (intégrée, lecture seule)
migrations/                    Alembic : config/ (config.sqlite3) · main/ (rosalie.sqlite3)
webui/                         le site : React + React Router + Tailwind (Vite) → webui/dist
finetune/                      fine-tuning, séparé du bot
tests/                         python bot.py test
docs/                          cette documentation
```
