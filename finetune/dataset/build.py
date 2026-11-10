"""Construit le dataset d'entraînement final (train / valid) pour mlx-lm.

    python finetune/dataset/build.py            # 10 % des exemples en validation
    python finetune/dataset/build.py 0.05

Sources :
  finetune/data/samples/*.jsonl          conversations converties (finetune/collect/)
  storages/dataset/samples.jsonl         exemples ⭐ / « Corriger (Gideon) » collectés par le bot

Résultat : finetune/data/mlx/{train,valid}.jsonl
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from libs.config import Config  # noqa: E402
from libs.conversation.prompt import build_system_prompt  # noqa: E402
from libs.llm.persona import Persona  # noqa: E402

SAMPLES_DIR = ROOT / "finetune" / "data" / "samples"
OUTPUT_DIR = ROOT / "finetune" / "data" / "mlx"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    samples = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"{path.name}:{line_number} JSON invalide, ignoré")
    return samples


def main():
    load_dotenv(ROOT / ".env")
    config = Config.from_env()
    valid_ratio = float(sys.argv[1]) if len(sys.argv) > 1 else 0.1

    sources = sorted(SAMPLES_DIR.glob("*.jsonl")) + [config.storage_dir / "dataset" / "samples.jsonl"]
    # Les exemples sans prompt système (conversations importées) reçoivent le persona actuel
    system = build_system_prompt(Persona(config.persona_file).text, "Gideon", "en message privé")

    samples = []
    for path in sources:
        rows = read_jsonl(path)
        kept = 0
        for row in rows:
            messages = row.get("messages", [])
            if len(messages) < 2 or messages[-1].get("role") != "assistant":
                continue
            if messages[0].get("role") != "system":
                messages = [{"role": "system", "content": system}, *messages]
            samples.append({"messages": messages})
            kept += 1
        if rows:
            print(f"- {path.relative_to(ROOT)} : {kept} exemples")

    if len(samples) < 100:
        print(f"⚠️ Seulement {len(samples)} exemples : vise au moins ~200 pour changer vraiment sa personnalité.")

    random.seed(42)
    random.shuffle(samples)
    valid_size = max(1, int(len(samples) * valid_ratio)) if len(samples) > 1 else 0
    valid, train = samples[:valid_size], samples[valid_size:]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("valid", valid)):
        with (OUTPUT_DIR / f"{name}.jsonl").open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Dataset : {len(train)} train / {len(valid)} valid -> {OUTPUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
