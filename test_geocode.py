"""
Diagnostic: teste l'API de géocodage avec 3 adresses et affiche la réponse brute.
Lance : python test_geocode.py
"""
import requests, csv, io

csv_body = "id,adresse\n1,BRUNOY 91800\n2,PARIS 75001\n3,US 95450\n4,VERSAILLES 78000\n"

print("=== Envoi CSV ===")
print(csv_body)

resp = requests.post(
    "https://api-adresse.data.gouv.fr/search/csv/",
    files={"data": ("addr.csv", csv_body.encode("utf-8"), "text/csv")},
    data=[("columns", "adresse")],
    timeout=30,
)

print(f"Status: {resp.status_code}")
print(f"\n=== Réponse brute (500 premiers chars) ===")
print(repr(resp.text[:500]))

print(f"\n=== Réponse CSV parsée ===")
reader = csv.DictReader(io.StringIO(resp.text))
print("Colonnes:", reader.fieldnames)
for i, row in enumerate(reader):
    print(f"Row {i+1}:", dict(row))
    if i >= 2:
        break
