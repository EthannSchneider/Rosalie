# Fine-tuning de Rosalie

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
    export_ollama.sh            conversion GGUF + import dans Ollama
    lora_config.yaml            réglages de l'entraînement
  tests/                      tests de ce dossier
  data/                       ⚠️ privé, ignoré par git
    raw/discord/<id>/messages.txt   conversations Discord brutes
    raw/whatsapp/*.zip              exports WhatsApp
    samples/*.jsonl                 exemples convertis, un fichier par conversation
    mlx/{train,valid}.jsonl         dataset final pour mlx-lm
  output/                     ⚠️ ignoré par git : adapters LoRA et modèle fusionné
  tools/llama.cpp/            ignoré par git : outils de conversion GGUF
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

`--assistant` choisit les messages de qui deviennent les réponses de Rosalie :
`them` (l'autre personne), `me` (toi) ou `both` (les deux, style mélangé). Les messages
des autres personnes demandent leur accord.

Le nettoyage retire médias, appels, messages supprimés et messages système, et remplace
liens, e-mails et numéros de téléphone. Une pause de plus de 3 h démarre une nouvelle
conversation.

## 2. Construire le dataset

```bash
python finetune/dataset/build.py
```

Assemble `data/samples/*.jsonl` et les exemples ⭐ / « Corriger (Rosalie) » collectés par
le bot (`storages/dataset/samples.jsonl`), ajoute le persona comme prompt système, et
écrit `data/mlx/train.jsonl` / `valid.jsonl`.

## 3. Entraîner

```bash
./finetune/training/train.sh
```

QLoRA sur Qwen3-8B en 4 bits (~10 Go de RAM, ferme Ollama). Réglages dans
`training/lora_config.yaml` : avec `iters: 600`, seuls ~600 exemples sont vus ; une passe complète
sur un gros dataset prend plusieurs heures.

### Import dans Ollama (local)

```bash
./finetune/training/export_ollama.sh
```

Télécharge et compile llama.cpp dans `finetune/tools/` (une seule fois), convertit le modèle
fusionné en GGUF, le compresse en Q4_K_M (~5 Go, comme `qwen3:8b`) et crée le modèle `rosalie`
dans Ollama avec le template de `qwen3:8b` (outils et réflexion on/off conservés).
Il faut ~20 Go libres pendant la conversion. Ensuite, dans `.env` : `OLLAMA_MODEL=rosalie`
(garder `DECIDER_MODEL=qwen3:8b` pour le tri des messages et les notes).
`finetune/output/fused` peut être supprimé : `train.sh --no-train` le recrée depuis les adapters.

Pourquoi pas plus simple : Ollama 0.40 ne charge plus les adaptateurs LoRA, et l'import direct
des safetensors choisit un mauvais template (réflexion qui fuit, plus d'outils).

## Tests

```bash
python -m unittest discover -s finetune/tests -t .
```
