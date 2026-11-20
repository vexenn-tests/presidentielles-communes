"""
Contrôle qualité : compare le 1er tour 2017 du moteur au fichier officiel
« Résultats définitifs du 1er tour par communes » (Ministère de l'Intérieur).
Usage : py scripts/verifier_2017.py   (fichier attendu : data/verif/2017_t1.xls)
"""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verifier_2022 import load_engine, key, ZDEP, ROOT  # noqa: E402

idx, data, aliases = load_engine()
ei = [e["id"] for e in idx["elections"]].index("2017_pres_t1")
names = [key(c["n"]) for c in idx["elections"][ei]["cands"]]

df = pd.read_excel(os.path.join(ROOT, "data", "verif", "2017_t1.xls"), header=None, dtype=str)
hdr = next(i for i in range(10) if "Inscrits" in df.iloc[i].tolist())
cols = df.iloc[hdr].tolist()
df = df.iloc[hdr + 1:]
ci = {c: cols.index(c) for c in ("Code du département", "Code de la commune", "Inscrits", "Votants", "Exprimés")}
first_nom = cols.index("Nom")

ok = diff = merged = absent = 0
ex = []
for row in df.itertuples(index=False):
    dep, com = str(row[ci["Code du département"]]), str(row[ci["Code de la commune"]])
    if dep in ("ZZ", "nan"):
        continue
    code = (ZDEP[dep] + com.zfill(3)) if dep in ZDEP else (dep.zfill(2) + com.zfill(3))
    ins, vot, exp = int(row[ci["Inscrits"]]), int(row[ci["Votants"]]), int(row[ci["Exprimés"]])
    theirs = {}
    for i in range(first_nom, len(row) - 2, 7):
        if isinstance(row[i], str) and row[i] != "nan":
            theirs[key(row[i])] = int(float(row[i + 2]))
    rec = (data.get(code) or [None] * 10)[ei]
    if rec is None:
        absent += 1
        continue
    mine = dict(zip(names, rec[3:]))
    if rec[0] == ins and rec[1] == vot and rec[2] == exp and all(mine.get(n) == v for n, v in theirs.items()):
        ok += 1
    elif aliases.get(code):
        merged += 1
    else:
        diff += 1
        if len(ex) < 8:
            ex.append((code, rec[:3], (ins, vot, exp)))
print(f"2017_pres_t1 : identiques {ok} | écarts {diff} | écarts dus à une fusion postérieure {merged} | absentes {absent}")
for e in ex:
    print("   ex.", e)
