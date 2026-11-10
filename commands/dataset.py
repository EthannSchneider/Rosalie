import json
import random
import sys

from libs.config import ROOT_DIR, Config
from libs.conversation.prompt import build_system_prompt
from libs.llm.persona import Persona
from libs.log import Log


def _read_jsonl(path):
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
                Log.warning(f"{path.name}:{line_number} invalid JSON, skipped")
    return samples


def run():
    """python bot.py dataset [valid_ratio]

    Fusionne finetune/seed.jsonl (exemples écrits à la main) et les exemples
    collectés sur Discord (⭐ / « Corriger ») en train.jsonl / valid.jsonl
    au format chat de mlx-lm.
    """
    config = Config.from_env()
    valid_ratio = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1

    seed = _read_jsonl(ROOT_DIR / "finetune" / "seed.jsonl")
    collected = _read_jsonl(config.storage_dir / "dataset" / "samples.jsonl")

    # Les exemples écrits à la main n'ont pas de prompt système : on met le persona actuel
    system = build_system_prompt(Persona(config.persona_file).text, "Gideon", "en message privé")

    samples = []
    for sample in seed + collected:
        messages = sample.get("messages", [])
        if len(messages) < 2 or messages[-1].get("role") != "assistant":
            continue
        if messages[0].get("role") != "system":
            messages = [{"role": "system", "content": system}, *messages]
        samples.append({"messages": messages})

    if len(samples) < 100:
        Log.warning(f"Only {len(samples)} samples: vise au moins ~200 pour un "
                    "fine-tune qui change vraiment sa personnalité.")

    random.seed(42)
    random.shuffle(samples)
    valid_size = max(1, int(len(samples) * valid_ratio)) if len(samples) > 1 else 0
    valid, train = samples[:valid_size], samples[valid_size:]

    out_dir = ROOT_DIR / "finetune" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("valid", valid)):
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")

    Log.info(f"Dataset written to {out_dir}: {len(train)} train / {len(valid)} valid "
             f"({len(seed)} seed + {len(collected)} collected)")
