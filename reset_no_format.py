#!/usr/bin/env python3
"""
Remet à zéro les tournois marqués no_format_in_html=True dans tous les
fichiers JSON du dossier data/, pour qu'ils soient re-enrichis au prochain run.

Usage:
    python reset_no_format.py
    python reset_no_format.py --dry-run   # voir sans modifier
"""
import argparse
import json
import os

DATA_DIR = "data"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    json_files = [
        os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR)
        if f.startswith("tournaments_") and f.endswith(".json")
        and not f.startswith("tournaments_france")
    ]

    total_reset = 0
    for jf in sorted(json_files):
        with open(jf, encoding="utf-8") as f:
            data = json.load(f)

        reset = 0
        for t in data.get("tournaments", []):
            e = t.get("enriched", {})
            if e.get("no_format_in_html") and not e.get("format"):
                del e["no_format_in_html"]
                reset += 1

        if reset:
            print(f"{jf}: {reset} tournois réinitialisés")
            if not args.dry_run:
                with open(jf, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        total_reset += reset

    print(f"\nTotal: {total_reset} tournois remis à zéro" + (" (dry-run)" if args.dry_run else ""))

if __name__ == "__main__":
    main()
