# Utilisation

## Quand répond-elle ?

1. **Jamais** aux messages commençant par `//` (`IGNORE_PREFIXES`), ni à quelqu'un d'autre que
   ses owners (comptes liés à Discord dont le rôle a au moins une permission `act.*`) si `public_replies` est sur non.
2. **Toujours** quand on lui parle directement : en tête-à-tête (DM Discord, terminal),
   @mention, réponse à un de ses messages, son nom dans le message (`ROSALIE_NAMES`).
   Dans ces cas elle ne peut pas choisir le silence.
3. **Conversation dédiée** (`/rosalie here` ou le réglage *Salons dédiés*) : à tous tes messages.
4. **Conversation en cours** : pendant `CONVERSATION_TIMEOUT` s, elle te suit sans être
   nommée ; un petit appel au modèle (OUI/NON) tranche les cas ambigus. `/rosalie stop` pour couper.

Les personnes qui ne sont pas ses owners peuvent discuter avec elle (avec un délai anti-spam,
`PUBLIC_COOLDOWN`), chercher une info ou la météo — mais elle n'agit pas pour elles et ne
leur dit rien de privé.

## Plus qu'un répondeur

- **Elle attend que tu aies fini** : après ton message, elle patiente `REPLY_DELAY` s (plus
  longtemps si tu es en train d'écrire, max `REPLY_MAX_WAIT` s) et répond à l'ensemble.
- **Elle peut se taire** quand un message n'appelle pas de réponse (« ok », « merci ») : rien
  n'est envoyé, un ✅ si elle a quand même agi. Jamais quand on lui pose une question.
- **Elle peut parler en plusieurs temps** : « je regarde ça » tout de suite, puis le résultat.
- **Longues tâches** : elle peut enchaîner jusqu'à `MAX_TOOL_STEPS` actions (50, `0` = sans
  limite) et t'envoie un **point d'étape** toutes les `progress_every` actions (6) : ce qu'elle
  a fait, trouvé, et ce qu'elle fait ensuite.
- **Elle peut revenir plus tard** : rappel, prendre des nouvelles, relancer, réponse plus
  réfléchie. Au moment venu, elle décide encore si c'est toujours utile.
- **Heartbeat** (toutes les `HEARTBEAT_INTERVAL` s) : déclenche les relances, et toutes les
  `INITIATIVE_EVERY` min, si vous n'avez pas parlé depuis `INITIATIVE_MIN_SILENCE` min, elle a
  un *moment de réflexion* dans ta dernière conversation (quelle que soit l'interface) : elle
  t'écrit si elle a une vraie raison, sinon silence. Jamais pendant `QUIET_HOURS`, max
  `INITIATIVE_MAX_PER_DAY` par jour, et jamais deux fois de suite sans réponse de ta part.
- **Erreurs** : si une action échoue, c'est toujours dit à la fin de sa réponse.

## Mémoire

- **Court terme** : les `HISTORY_SIZE` derniers messages de chaque conversation
  (`storages/memory/`).
- **Long terme** (`storages/long_term.sqlite3`), partagée entre toutes les interfaces :
  - après chaque échange, un appel en arrière-plan note les faits durables
    (« Le chat d'Ethann s'appelle Minou », dates converties en vraies dates) ;
  - elle peut aussi noter / chercher / oublier elle-même ;
  - à chaque message, les souvenirs liés au sujet + les plus importants sont mis dans son
    prompt ; si rien n'est trouvé, on lui dit de ne pas inventer.

## Commandes Discord

| Commande | Effet |
|---|---|
| `/rosalie status` | modèle, Ollama, mémoire, heartbeat, relances |
| `/rosalie model <nom>` | changer de modèle Ollama (enregistré dans les réglages) |
| `/rosalie here` | (dés)activer « répondre à tout » dans ce salon |
| `/rosalie reset` | effacer l'historique de ce salon (les souvenirs restent) |
| `/rosalie stop` | mettre fin à la conversation en cours |
| `/rosalie persona [nom]` | changer de personnalité, ou recharger l'actuelle |
| `/rosalie memories [recherche]` · `/rosalie forget <id>` | voir / effacer des souvenirs |
| `/rosalie agenda` · `/rosalie cancel <id>` | voir / annuler des relances |
| `/rosalie initiative true/false` | lui permettre ou non de t'écrire d'elle-même |
| `/reload` | recharger les commandes Discord |
| ⭐ sur une réponse · clic droit → *Corriger (Rosalie)* | exemples pour le fine-tuning |

## Terminal

`python bot.py chat` : tu es son créateur, tous ses outils
sont disponibles, les confirmations se font au clavier (`o` / `n`), les fichiers qu'elle
t'envoie (photos…) sont enregistrés dans `storages/terminal_files/`. `/quit` pour quitter.
Les logs vont dans `log.txt` sans encombrer la discussion.

## Fine-tuning de la personnalité

Tout est dans [`finetune/`](../finetune/README.md), séparé du bot : récupération de
conversations Discord / WhatsApp, conversion, dataset, entraînement. Côté bot, il ne reste
que la collecte d'exemples pendant que tu discutes avec elle sur Discord (⭐ et
*Corriger (Rosalie)* ; seules les réponses de discussion sont gardées, pas celles liées à une action).
