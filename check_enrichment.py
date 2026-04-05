#!/usr/bin/env python3
"""Vérifie l'état d'enrichissement de tous les fichiers de données."""
import json
import os

data_dir = "data"

files = sorted(
    f for f in os.listdir(data_dir)
    if f.startswith("tournaments_") and f.endswith(".json")
    and not f.startswith("tournaments_france")
)

total_ok = total_fail = total_no_fmt = total_unenriched = 0

for fn in files:
    with open(os.path.join(data_dir, fn), encoding="utf-8") as f:
        data = json.load(f)
    ts = data.get("tournaments", [])
    ok = fail = no_fmt = unenriched = 0
    for t in ts:
        e = t.get("enriched", {})
        if "enriched" not in t:
            unenriched += 1
        elif e.get("fetch_failed"):
            fail += 1
        elif e.get("no_format_in_html"):
            no_fmt += 1
        elif e.get("format"):
            ok += 1
        else:
            unenriched += 1
    status = f"ok={ok:4d}  fail={fail:3d}  no_fmt={no_fmt:3d}  unenriched={unenriched:3d}"
    print(f"{fn}: {len(ts):4d} tournois | {status}")
    total_ok += ok
    total_fail += fail
    total_no_fmt += no_fmt
    total_unenriched += unenriched

total = total_ok + total_fail + total_no_fmt + total_unenriched
print(f"\nTOTAL: {total} tournois (avec doublons)")
print(f"  ✅ ok           : {total_ok}")
print(f"  ❌ fetch_failed : {total_fail}  ← seront retentés au prochain --enrich-only")
print(f"  ⚠️  no_format   : {total_no_fmt}  ← pages JS-rendues, format indisponible")
print(f"  ⬜ non traités  : {total_unenriched}")
