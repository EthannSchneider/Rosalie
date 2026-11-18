# Conteneurs Docker

Rosalie peut créer ses propres **conteneurs Docker** et y lancer **n'importe quelle commande** :
installer des paquets, écrire et lancer des scripts, faire tourner un serveur ou une base de
données, essayer un outil… C'est son **bac à sable** : ce qui s'y passe ne touche pas à la
machine. Le modèle de code de l'[évolution du code](evolution.md) y travaille aussi.

Il n'y a **pas de confirmation** : la sécurité vient de l'isolation, pas d'un bouton.

## Activer

Docker doit être installé et lancé sur la machine de Rosalie.

```bash
python bot.py settings set containers oui
```

Pour un autre rôle que superadmin : site → *Rôles* → cocher **Conteneurs Docker** (ou
`python bot.py roles set <rôle> <liste complète des permissions>`, avec `act.containers`).

| Réglage (onglet Conteneurs) | Rôle |
|---|---|
| `containers` | active les conteneurs (désactivés par défaut) |
| `containers_image` | image utilisée quand elle n'en précise pas (`python:3.13-slim`) |
| `containers_max` | nombre max de conteneurs à elle en même temps (5) |
| `containers_memory` · `containers_cpus` | limites par conteneur (`2g`, 2 processeurs) |
| `containers_timeout` | durée max d'une commande (120 s) |
| `containers_network` | accès réseau des conteneurs (oui) |

Permission : **`act.containers`**. Le superadmin l'a d'office ; elle n'est donnée à aucun autre
rôle automatiquement (ni à `admin`, ni aux rôles existants) : à toi de l'ajouter. Quand le
réglage est coupé, les outils ne sont même pas proposés au modèle (ils ne coûtent aucun contexte).

## Les outils

| Outil | Ce qu'il fait |
|---|---|
| `container_run` | crée et démarre un conteneur : nom, image, commande de démarrage, ports, variables |
| `container_exec` | lance une commande shell dans un conteneur et renvoie sa sortie |
| `container_logs` | derniers journaux d'un conteneur |
| `container_list` | ses conteneurs (nom, image, état, ports) |
| `container_remove` | arrête et supprime un conteneur |

Sans commande, le conteneur attend (`sleep infinity`) et elle y travaille avec `container_exec`.
Avec `command="image"`, il lance le service prévu par l'image (nginx, postgres…). Un conteneur
reste en place jusqu'à ce qu'elle (ou toi : `docker rm -f rosalie-…`) le supprime.

## Garde-fous

Ils sont appliqués par le code (`libs/containers/docker.py`), pas par le modèle :

- **nom toujours préfixé `rosalie-`** (ajouté d'office ; caractères limités) ;
- **seulement ses conteneurs** : chacun porte l'étiquette `rosalie.managed=true`, vérifiée avant
  chaque action. Un conteneur à toi dont le nom commence par `rosalie-` (celui de Docker Compose,
  `rosalie-rosalie-1`) est hors de portée ; les conteneurs `rosalie-evolve-…` de l'évolution du
  code aussi ;
- **aucun dossier de la machine** n'est monté, pas de socket Docker, jamais de `--privileged` ni
  de réseau de l'hôte : les arguments de `docker run` sont construits par le code, le modèle ne
  fournit que le nom, l'image, la commande, les ports et les variables (tous validés) ;
- **ressources limitées** : mémoire, processeurs, nombre de processus, `no-new-privileges` ;
- **ports publiés sur `127.0.0.1` seulement** (ports de l'hôte ≥ 1024) ;
- durée max par commande, appliquée dans le conteneur ; sortie tronquée.

⚠️ À savoir :

- avec `containers_network` sur oui, un conteneur accède à **internet et à ton réseau local**
  (y compris les services de la machine via `host.docker.internal`). Les outils web de Rosalie
  refusent les adresses locales ; un conteneur, non. Mets `containers_network` sur non pour
  couper tout réseau ;
- un conteneur partage le noyau de la machine : c'est une isolation solide pour un usage
  personnel, pas une machine virtuelle ;
- les images viennent du registre Docker : elle peut télécharger n'importe quelle image publique ;
- si Rosalie tourne **elle-même dans Docker**, elle n'a pas de commande `docker` : la
  fonctionnalité n'y est pas disponible (ne lui donne pas le socket Docker : ce serait lui donner
  la machine).

## Code

| Fichier | Rôle |
|---|---|
| `libs/containers/docker.py` | `Docker` : commande `docker`, noms, étiquette, limites |
| `libs/assistant/tools/containers.py` | les outils `container_*` |
| `libs/evolve/sandbox.py` | conteneur de travail de l'évolution du code |
| `tests/test_containers.py` | tests (fausse commande `docker`) |
