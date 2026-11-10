"""Récupère tout l'historique d'une conversation privée Discord puis le convertit en dataset.

    python finetune/collect/export_discord.py <channel_id> --assistant them
    python finetune/collect/export_discord.py <channel_id> --assistant me
    python finetune/collect/export_discord.py <channel_id> --assistant both
    python finetune/collect/export_discord.py <channel_id> --assistant them --before 1562918208212697222
    python finetune/collect/export_discord.py <channel_id> --assistant them --convert-only

--assistant : les messages de qui deviennent les réponses de Gideon
              (« them » = l'autre personne, « me » = toi, « both » = les deux points de vue :
              deux fois plus d'exemples, mais un style mélangé).

Le token de ton compte est lu dans la variable DISCORD_USER_TOKEN ou demandé (saisie
masquée). Il n'est jamais écrit sur le disque.

⚠️ Utiliser le token d'un compte utilisateur dans un script est contraire aux conditions de
Discord : ton compte peut être limité ou banni. Les pauses réduisent le risque, sans l'annuler.

Fichiers (privés, ignorés par git) :
  finetune/data/raw/discord/<channel_id>/messages.txt  un message JSON par ligne (reprise possible)
  finetune/data/samples/discord_<channel_id>.jsonl     exemples pour `python finetune/dataset/build.py`
"""
import argparse
import getpass
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from finetune.dataset.converter import convert  # noqa: E402

API = "https://discord.com/api/v9"
BATCH = 50
PAUSE = (1.0, 20.0)
RETRY_BASE = 30        # secondes avant le 1er nouvel essai après une erreur réseau
RETRY_MAX = 600        # puis double à chaque échec, jusqu'à 10 min
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:159.0) "
              "Gecko/20100101 Firefox/159.0")


def request(path: str, token: str):
    req = urllib.request.Request(f"{API}{path}", headers={
        "Authorization": token,
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "fr-CH,fr;q=0.9,en;q=0.8",
        "X-Discord-Locale": "fr",
        "X-Discord-Timezone": "Europe/Zurich",
        "Referer": "https://discord.com/channels/@me",
    })
    failures = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429:   # trop de requêtes : Discord dit combien attendre
                wait = float(json.loads(error.read() or b"{}").get("retry_after", 30)) + 5
                print(f"  limite atteinte, pause de {wait:.0f}s")
                time.sleep(wait)
                continue
            if error.code == 401:
                sys.exit("Token refusé (401) : il a peut-être été réinitialisé.")
            if error.code in (403, 404):
                sys.exit(f"Accès refusé à ce salon ({error.code}).")
            if error.code < 500:
                raise
            reason = f"erreur serveur {error.code}"
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError) as error:
            reason = str(getattr(error, "reason", error))
        # Connexion coupée, timeout, Discord en panne… : on attend puis on réessaie
        failures += 1
        wait = min(RETRY_BASE * 2 ** (failures - 1), RETRY_MAX)
        print(f"  problème réseau ({reason}), nouvel essai dans {wait:.0f}s (essai {failures})")
        time.sleep(wait)


def oldest_saved_id(path: Path) -> str | None:
    if not path.exists():
        return None
    ids = [int(json.loads(line)["id"]) for line in path.open(encoding="utf-8") if line.strip()]
    return str(min(ids)) if ids else None


def export(channel_id: str, token: str, messages_path: Path, start_before: str | None = None):
    """Remonte l'historique bloc par bloc : chaque requête demande les messages
    `before` le plus ancien déjà reçu, jusqu'au tout premier message."""
    messages_path.parent.mkdir(parents=True, exist_ok=True)
    saved = oldest_saved_id(messages_path)
    before = min((x for x in (saved, start_before) if x), key=int, default=None)
    if before:
        print(f"Départ : messages plus anciens que {before}")
    total = 0
    with messages_path.open("a", encoding="utf-8") as file:
        while True:
            query = f"?limit={BATCH}" + (f"&before={before}" if before else "")
            batch = request(f"/channels/{channel_id}/messages{query}", token)
            if not batch:
                break
            for message in batch:
                file.write(json.dumps(message, ensure_ascii=False) + "\n")
            file.flush()
            total += len(batch)
            before = batch[-1]["id"]   # l'API renvoie du plus récent au plus ancien
            print(f"  {total} messages (jusqu'au {batch[-1]['timestamp'][:10]})")
            if len(batch) < BATCH:
                break
            pause = random.uniform(*PAUSE)
            time.sleep(pause)
    print(f"Export terminé : {total} nouveaux messages -> {messages_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("channel_id")
    parser.add_argument("--assistant", choices=("me", "them", "both"), required=True,
                        help="les messages de qui deviennent les réponses de Gideon")
    parser.add_argument("--before", help="id d'un message : commencer à partir des messages plus anciens")
    parser.add_argument("--convert-only", action="store_true",
                        help="ne télécharge rien, reconvertit messages.txt")
    args = parser.parse_args()

    messages_path = ROOT / "finetune" / "data" / "raw" / "discord" / args.channel_id / "messages.txt"
    output_path = ROOT / "finetune" / "data" / "samples" / f"discord_{args.channel_id}.jsonl"

    token = os.getenv("DISCORD_USER_TOKEN") or getpass.getpass("Token Discord (masqué) : ")
    me = request("/users/@me", token)["id"]
    if not args.convert_only:
        try:
            export(args.channel_id, token, messages_path, args.before)
        except KeyboardInterrupt:
            print("\nArrêté : conversion de ce qui a déjà été récupéré (relance pour continuer).")

    authors = {json.loads(line)["author"]["id"] for line in messages_path.open(encoding="utf-8") if line.strip()}
    others = sorted(authors - {me})
    if args.assistant != "me" and len(others) != 1:
        sys.exit(f"« {args.assistant} » est ambigu : {len(others)} autres personnes dans ce salon.")
    assistant_ids = {"me": [me], "them": others, "both": [me, *others]}[args.assistant]

    sessions, samples = convert(messages_path, output_path, assistant_ids)
    print(f"Dataset : {samples} exemples tirés de {sessions} conversations -> {output_path}")
    print("Ensuite : python finetune/dataset/build.py   (puis ./finetune/training/train.sh)")


if __name__ == "__main__":
    main()
