"""Affiche le statut d'enrichissement des nouveaux tournois du dernier fichier modifié."""
import json, os, sys, glob

# Utilise le fichier passé en argument ou le plus récemment modifié
if len(sys.argv) > 1:
    path = sys.argv[1]
else:
    files = glob.glob("data/tournaments_*.json")
    files = [f for f in files if "france_entiere" not in f]
    path = max(files, key=os.path.getmtime)

print(f"Fichier : {path}\n")

with open(path, encoding="utf-8") as f:
    data = json.load(f)

tournaments = data.get("tournaments", [])
new_ones = [t for t in tournaments if t.get("_is_new")]

if not new_ones:
    print("Aucun tournoi marqué _is_new dans ce fichier.")
    print("(Les _is_new sont remis à False après génération HTML — vérifier fetch_failed/no_fmt sur tous)")
    new_ones = [t for t in tournaments if not t.get("enriched", {}).get("format")]
    print(f"\nTournois SANS format ({len(new_ones)}) :\n")

for t in new_ones[:20]:
    e = t.get("enriched", {})
    status = ""
    if e.get("fetch_failed"):       status = "❌ FETCH_FAILED (cookie expiré ou réseau)"
    elif e.get("no_format_in_html"): status = "⚠️  NO_FORMAT_IN_HTML (page sans div format)"
    elif e.get("format"):            status = f"✅ format={e['format']}"
    elif not e:                      status = "⬜ pas encore enrichi"
    else:                            status = "❓ enrichi mais sans format ni flag"
    print(f"  {t.get('libelle','')[:45]:<45} | {status}")
