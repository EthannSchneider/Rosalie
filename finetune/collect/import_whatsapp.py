"""Convertit les exports WhatsApp de finetune/data/raw/whatsapp/ en dataset.

    python finetune/collect/import_whatsapp.py --assistant both
    python finetune/collect/import_whatsapp.py --assistant them --me "Ethann Schneider"

Dans WhatsApp : ouvrir la discussion > nom du contact > Exporter la discussion > Sans médias,
puis déposer le .zip (ou le _chat.txt) dans finetune/data/raw/whatsapp/.

--assistant : les messages de qui deviennent les réponses de Gideon
              (« them » = l'autre personne, « me » = toi, « both » = les deux points de vue).
--me        : ton nom tel qu'il apparaît dans les exports. Par défaut, la personne présente
              dans tous les exports (toi), s'il y en a plusieurs.

Résultat : finetune/data/samples/whatsapp_<contact>.jsonl, pris en compte par `python finetune/dataset/build.py`.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finetune.dataset.converter import load_whatsapp, whatsapp_authors, write_samples  # noqa: E402

SOURCE = ROOT / "finetune" / "data" / "raw" / "whatsapp"
OUTPUT = ROOT / "finetune" / "data" / "samples"


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "chat"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assistant", choices=("me", "them", "both"), required=True)
    parser.add_argument("--me", help="ton nom dans les exports WhatsApp")
    args = parser.parse_args()

    files = sorted(p for p in SOURCE.glob("*") if p.suffix in (".zip", ".txt"))
    if not files:
        sys.exit(f"Aucun export dans {SOURCE}")

    authors = {path: whatsapp_authors(path) for path in files}
    me = args.me
    if not me:
        common = set.intersection(*authors.values()) if len(files) > 1 else set()
        if len(common) != 1:
            sys.exit("Impossible de deviner ton nom : précise --me \"Ton Nom\".")
        me = common.pop()
    print(f"Toi : {me}")

    total = 0
    for path in files:
        others = sorted(authors[path] - {me})
        if me not in authors[path]:
            print(f"- {path.name} : ignoré ({me} n'y apparaît pas)")
            continue
        if args.assistant != "me" and len(others) != 1:
            print(f"- {path.name} : ignoré (discussion de groupe, {len(others)} autres personnes)")
            continue
        assistants = {"me": [me], "them": others, "both": [me, *others]}[args.assistant]
        contact = others[0] if others else path.stem
        output = OUTPUT / f"whatsapp_{slug(contact)}.jsonl"
        messages = load_whatsapp(path)
        sessions, samples = write_samples(messages, output, assistants)
        total += samples
        print(f"- {contact} : {len(messages)} messages, {sessions} conversations -> "
              f"{samples} exemples ({output.relative_to(ROOT)})")

    print(f"Total : {total} exemples. Ensuite : python finetune/dataset/build.py   (puis ./finetune/training/train.sh)")


if __name__ == "__main__":
    main()
