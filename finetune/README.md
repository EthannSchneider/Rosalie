# Fine-tuning de Gideon

Tout ce qui sert à entraîner sa personnalité vit ici, séparé du bot : récupération des
conversations, conversion, construction du dataset et entraînement. Rien de ce dossier
n'est copié dans l'image Docker du bot.

```
finetune/
  README.md
  requirements.txt            dépendances du fine-tuning (venv séparé : finetune/.venv)
  collect/                    1. récupérer les conversations
    export_discord.py           télécharge une conversation privée Discord
    import_whatsapp.py          convertit les exports WhatsApp
  dataset/                    2. préparer les données
    converter.py                logique commune : nettoyage, conversations, exemples
    build.py                    assemble le dataset final train / valid
  training/                   3. entraîner
    train.sh                    entraînement LoRA (mlx-lm) + fusion
    lora_config.yaml            réglages de l'entraînement
  tests/                      tests de ce dossier
  data/                       ⚠️ privé, ignoré par git
    raw/discord/<id>/messages.txt   conversations Discord brutes
    raw/whatsapp/*.zip              exports WhatsApp
    samples/*.jsonl                 exemples convertis, un fichier par conversation
    mlx/{train,valid}.jsonl         dataset final pour mlx-lm
  output/                     ⚠️ ignoré par git : adapters LoRA et modèle fusionné
```

## 1. Récupérer des conversations

**Discord** (conversation privée) :

```bash
python finetune/collect/export_discord.py <channel_id> --assistant them|me|both [--before <message_id>]
```

- Remonte l'historique par blocs de 50 avec `before`, pause aléatoire de 1 à 20 s.
- Reprend tout seul là où il s'est arrêté ; réessaie en cas de coupure réseau.
- Le token est demandé au lancement (ou `DISCORD_USER_TOKEN`) et jamais enregistré.
- ⚠️ Un script sur un compte utilisateur est contraire aux conditions de Discord.

**WhatsApp** : discussion → nom du contact → *Exporter la discussion* → *Sans médias*,
dépose les `.zip` dans `finetune/data/raw/whatsapp/`, puis :

```bash
python finetune/collect/import_whatsapp.py --assistant them|me|both [--me "Ton Nom"]
```

`--assistant` choisit les messages de qui deviennent les réponses de Gideon :
`them` (l'autre personne), `me` (toi) ou `both` (les deux, style mélangé). Les messages
des autres personnes demandent leur accord.

Le nettoyage retire médias, appels, messages supprimés et messages système, et remplace
liens, e-mails et numéros de téléphone. Une pause de plus de 3 h démarre une nouvelle
conversation.

## 2. Construire le dataset

```bash
python finetune/dataset/build.py
```

Assemble `data/samples/*.jsonl` et les exemples ⭐ / « Corriger (Gideon) » collectés par
le bot (`storages/dataset/samples.jsonl`), ajoute le persona comme prompt système, et
écrit `data/mlx/train.jsonl` / `valid.jsonl`.

## 3. Entraîner

```bash
./finetune/training/train.sh
```

QLoRA sur Qwen3-8B en 4 bits (~10 Go de RAM, ferme Ollama). Réglages dans
`training/lora_config.yaml` : avec `iters: 600`, seuls ~600 exemples sont vus ; une passe complète
sur un gros dataset prend plusieurs heures.

**Import dans Ollama : en attente.** Ollama 0.40 ne charge plus les adaptateurs LoRA et
l'import direct du modèle fusionné perd le template (réflexion qui fuit, plus d'outils).
La voie fiable : conversion GGUF avec llama.cpp + template de `qwen3:8b`.

## Tests

```bash
python -m unittest discover -s finetune/tests -t .
```
