#!/usr/bin/env bash
# Fine-tune la personnalité de Rosalie sur Apple Silicon (mlx-lm). Import : export_ollama.sh.
#
#   ./finetune/training/train.sh             # dataset -> LoRA -> fusion
#   ./finetune/training/train.sh --no-train  # refait seulement la fusion
#
# Variables : MLX_MODEL (sinon celui de lora_config.yaml), ITERS.
set -euo pipefail

# mlx n'existe qu'en arm64 : si ce shell tourne sous Rosetta (bash Homebrew Intel),
# on se relance en natif.
if [ "$(uname -m)" != "arm64" ] && [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    exec arch -arm64 /bin/bash "$0" "$@"
fi

cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
VENV="$ROOT/finetune/.venv"
# tr -d '\r' : ignore les fins de ligne Windows si le fichier en a (git core.autocrlf)
CONFIG_MODEL="$(grep '^model:' finetune/training/lora_config.yaml | tr -d '\r' | sed -E 's/model: *"?([^"]*)"?/\1/')"
MLX_MODEL="${MLX_MODEL:-$CONFIG_MODEL}"

if [ ! -x "$VENV/bin/mlx_lm.lora" ]; then
    echo "==> Création du venv de fine-tuning"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r finetune/requirements.txt
fi

if [ "${1:-}" != "--no-train" ]; then
    echo "==> Construction du dataset"
    "$VENV/bin/python" finetune/dataset/build.py

    echo "==> Libère la RAM : décharge les modèles Ollama"
    ollama ps | awk 'NR>1 {print $1}' | xargs -r -n1 ollama stop || true

    echo "==> Entraînement LoRA ($MLX_MODEL)"
    "$VENV/bin/mlx_lm.lora" --config finetune/training/lora_config.yaml --model "$MLX_MODEL" \
        ${ITERS:+--iters "$ITERS"}
fi

echo "==> Fusion des adapters dans le modèle (fp16)"
rm -rf finetune/output/fused
"$VENV/bin/mlx_lm.fuse" \
    --model "$MLX_MODEL" \
    --adapter-path finetune/output/adapters \
    --save-path finetune/output/fused \
    --dequantize

echo
echo "Entraînement et fusion OK : modèle fusionné dans finetune/output/fused."
echo "Import dans Ollama : ./finetune/training/export_ollama.sh"
