#!/usr/bin/env bash
# Fine-tune la personnalité de Gideon sur Apple Silicon (mlx-lm), puis l'importe dans Ollama.
#
#   ./finetune/train.sh             # dataset -> LoRA -> fusion -> ollama create gideon
#   ./finetune/train.sh --no-train  # refait seulement fusion + import
#
# Variables : OLLAMA_NAME (gideon), OLLAMA_BASE (qwen3:8b, pour récupérer le template
# du chat + outils), MLX_MODEL (sinon celui de lora_config.yaml), ITERS.
set -euo pipefail

# mlx n'existe qu'en arm64 : si ce shell tourne sous Rosetta (bash Homebrew Intel),
# on se relance en natif.
if [ "$(uname -m)" != "arm64" ] && [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    exec arch -arm64 /bin/bash "$0" "$@"
fi

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
VENV="$ROOT/finetune/.venv"
CONFIG_MODEL="$(grep '^model:' finetune/lora_config.yaml | sed -E 's/model: *"?([^"]*)"?/\1/')"
MLX_MODEL="${MLX_MODEL:-$CONFIG_MODEL}"
OLLAMA_NAME="${OLLAMA_NAME:-gideon}"
OLLAMA_BASE="${OLLAMA_BASE:-qwen3:8b}"

if [ ! -x "$VENV/bin/mlx_lm.lora" ]; then
    echo "==> Création du venv de fine-tuning"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r finetune/requirements.txt
fi

if [ "${1:-}" != "--no-train" ]; then
    echo "==> Construction du dataset"
    "$VENV/bin/python" bot.py dataset

    echo "==> Libère la RAM : décharge les modèles Ollama"
    ollama ps | awk 'NR>1 {print $1}' | xargs -r -n1 ollama stop || true

    echo "==> Entraînement LoRA ($MLX_MODEL)"
    "$VENV/bin/mlx_lm.lora" --config finetune/lora_config.yaml --model "$MLX_MODEL" \
        ${ITERS:+--iters "$ITERS"}
fi

echo "==> Fusion des adapters dans le modèle (fp16)"
rm -rf finetune/fused
"$VENV/bin/mlx_lm.fuse" \
    --model "$MLX_MODEL" \
    --adapter-path finetune/adapters \
    --save-path finetune/fused \
    --dequantize

# Import dans Ollama : EN ATTENTE.
# Ollama 0.40 ne charge plus les adaptateurs LoRA, et l'import direct des safetensors
# fusionnés choisit un renderer « qwen3-coder » (réflexion qui fuit, pas d'outils).
# La voie fiable est une conversion GGUF (llama.cpp) + le template de qwen3:8b — voir README.
echo
echo "Entraînement et fusion OK : modèle fusionné dans finetune/fused."
echo "L'import dans Ollama n'est pas encore branché (voir README, section Fine-tuning)."
