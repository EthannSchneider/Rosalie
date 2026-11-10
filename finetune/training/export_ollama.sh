#!/usr/bin/env bash
# Importe le modèle fine-tuné (finetune/output/fused) dans l'Ollama local.
#
#   ./finetune/training/export_ollama.sh
#
# Étapes : safetensors fusionnés -> GGUF f16 (llama.cpp) -> GGUF Q4_K_M (~5 Go)
#          -> `ollama create` avec le template de qwen3:8b (chat, outils, think on/off).
# Rien ne sort de la machine. Variables : OLLAMA_NAME (rosalie), OLLAMA_BASE (qwen3:8b),
# QUANT (Q4_K_M), KEEP_GGUF=1 pour garder le .gguf après l'import.
set -euo pipefail

if [ "$(uname -m)" != "arm64" ] && [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    exec arch -arm64 /bin/bash "$0" "$@"
fi

cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
VENV="$ROOT/finetune/.venv"
OUT="$ROOT/finetune/output"
FUSED="$OUT/fused"
LLAMA="$ROOT/finetune/tools/llama.cpp"
OLLAMA_NAME="${OLLAMA_NAME:-rosalie}"
OLLAMA_BASE="${OLLAMA_BASE:-qwen3:8b}"
QUANT="${QUANT:-Q4_K_M}"
F16="$OUT/$OLLAMA_NAME-f16.gguf"
GGUF="$OUT/$OLLAMA_NAME-$(echo "$QUANT" | tr '[:upper:]' '[:lower:]').gguf"

[ -f "$FUSED/config.json" ] || { echo "Pas de modèle fusionné : lance d'abord train.sh"; exit 1; }
ollama show "$OLLAMA_BASE" >/dev/null 2>&1 || { echo "Modèle de base absent : ollama pull $OLLAMA_BASE"; exit 1; }

if [ ! -d "$LLAMA" ]; then
    echo "==> Téléchargement de llama.cpp (outils de conversion)"
    git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA"
fi

if ! "$VENV/bin/python" -c "import torch, gguf" >/dev/null 2>&1; then
    echo "==> Dépendances de conversion"
    "$VENV/bin/pip" install -q -r finetune/requirements.txt
    "$VENV/bin/pip" install -q -e "$LLAMA/gguf-py"
fi

QUANTIZE="$LLAMA/build/bin/llama-quantize"
if [ ! -x "$QUANTIZE" ]; then
    echo "==> Compilation de llama-quantize"
    # Le cmake de Homebrew Intel tourne sous Rosetta : « -mcpu=native » y désigne un CPU x86
    # et casse la compilation arm64. GGML_NATIVE=OFF laisse clang viser l'Apple Silicon par défaut.
    # Les bibliothèques de /usr/local (Homebrew Intel, ex. OpenSSL) sont x86_64 : on les ignore,
    # et llama-quantize n'a pas besoin de HTTPS.
    rm -rf "$LLAMA/build"
    cmake -S "$LLAMA" -B "$LLAMA/build" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_SYSTEM_PROCESSOR=arm64 -DGGML_NATIVE=OFF \
        -DCMAKE_IGNORE_PREFIX_PATH=/usr/local -DLLAMA_OPENSSL=OFF -DGGML_OPENMP=OFF \
        -DGGML_METAL=OFF -DLLAMA_BUILD_SERVER=OFF -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=OFF >/dev/null
    cmake --build "$LLAMA/build" --target llama-quantize -j >/dev/null
fi

if [ ! -f "$GGUF" ]; then
    echo "==> Conversion en GGUF f16 (~16 Go temporaires)"
    "$VENV/bin/python" "$LLAMA/convert_hf_to_gguf.py" "$FUSED" --outtype f16 --outfile "$F16"
    echo "==> Quantification $QUANT"
    "$QUANTIZE" "$F16" "$GGUF" "$QUANT" >/dev/null
    rm -f "$F16"
fi

echo "==> Modelfile (template et paramètres de $OLLAMA_BASE)"
MODELFILE="$OUT/Modelfile"
{
    echo "FROM $GGUF"
    printf 'TEMPLATE """%s"""\n' "$(ollama show "$OLLAMA_BASE" --template)"
    ollama show "$OLLAMA_BASE" --parameters | awk 'NF {print "PARAMETER", $0}'
} > "$MODELFILE"

echo "==> ollama create $OLLAMA_NAME"
ollama create "$OLLAMA_NAME" -f "$MODELFILE"

[ "${KEEP_GGUF:-0}" = "1" ] || rm -f "$GGUF"
echo
echo "OK : modèle « $OLLAMA_NAME » dans Ollama. Pour l'utiliser : OLLAMA_MODEL=$OLLAMA_NAME dans .env"
echo "finetune/output/fused (~16 Go) peut être supprimé : train.sh --no-train le recrée depuis les adapters."
