"""
Contrôle qualité : compare les données du moteur (data/dep/*.js) aux fichiers officiels
« Résultats définitifs par commune » de la présidentielle 2022 publiés par le Ministère de l'Intérieur.

Usage : py scripts/verifier_2022.py   (fichiers attendus dans data/verif/2022_t1.txt et 2022_t2.txt)
"""
import glob, json, os, re, sys, unicodedata
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZDEP = {"ZA": "97", "ZB": "97", "ZC": "97", "ZD": "97", "ZM": "97", "ZS": "97", "ZX": "97",
        "ZN": "98", "ZP": "98", "ZW": "98"}


def key(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s.upper().split()[-1]


def load_engine():
    txt = open(os.path.join(ROOT, "data", "index.js"), encoding="utf-8").read()
    idx = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
    data, aliases = {}, {}
    for c in idx["communes"]:
        aliases[c[0]] = c[4]
    for f in glob.glob(os.path.join(ROOT, "data", "dep", "*.js")):
        t = open(f, encoding="utf-8").read()
        data.update(json.loads(t[t.index(",") + 1:t.rindex(")")]))
    return idx, data, aliases


def load_official(path):
    res = {}
    with open(path, encoding="latin-1") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split(";")
            dep, com = p[0], p[2]
            if dep == "ZZ":
                continue
            code = (ZDEP[dep] + com) if dep in ZDEP else (dep.zfill(2) + com)
            ins, vot, exp = int(p[5]), int(p[8]), int(p[16])
            voix = {}
            for i in range(19, len(p) - 6, 7):
                if p[i + 2]:
                    voix[p[i + 2]] = int(p[i + 4])
            r = res.setdefault(code, [0, 0, 0, defaultdict(int)])
            r[0] += ins; r[1] += vot; r[2] += exp
            for n, v in voix.items():
                r[3][n] += v
    return res


def main():
    idx, data, aliases = load_engine()
    names = {e["id"]: [key(c["n"]) for c in e["cands"]] for e in idx["elections"]}
    for ei, (eid, fname) in enumerate([("2022_pres_t1", "2022_t1.txt"), ("2022_pres_t2", "2022_t2.txt")]):
        ei = [e["id"] for e in idx["elections"]].index(eid)
        off = load_official(os.path.join(ROOT, "data", "verif", fname))
        ok = diff = merged = absent = 0
        exemples = []
        winner_diff = egalites = winner_fusion = 0
        absents_ex = []
        for code, (ins, vot, exp, voix) in off.items():
            rec = (data.get(code) or [None] * 10)[ei]
            if rec is None:
                absent += 1
                absents_ex.append(code)
                continue
            mine = dict(zip(names[eid], rec[3:]))
            theirs = {key(n): v for n, v in voix.items()}
            same = rec[0] == ins and rec[1] == vot and rec[2] == exp and all(mine.get(n) == v for n, v in theirs.items())
            if same:
                ok += 1
            elif aliases.get(code):
                merged += 1  # commune fusionnée après 2022 : le moteur additionne les anciennes communes
            else:
                diff += 1
                if len(exemples) < 8:
                    exemples.append((code, (rec[0], rec[1], rec[2]), (ins, vot, exp)))
            if theirs and max(theirs, key=theirs.get) != max(mine, key=mine.get):
                top = sorted(theirs.values(), reverse=True)
                if same and len(top) > 1 and top[0] == top[1]:
                    egalites += 1  # égalité de voix : les deux sont « en tête »
                elif same:
                    winner_diff += 1
                else:
                    winner_fusion += 1
        print(f"{eid}: {len(off)} communes officielles | identiques {ok} | écarts {diff} | "
              f"écarts dus à une fusion postérieure {merged} | absentes du moteur {absent} | "
              f"vainqueur différent : {winner_diff} (+ {egalites} égalités de voix, {winner_fusion} communes fusionnées)")
        if ei % 2 == 0:
            # Les communes absentes doivent avoir été absorbées : leurs voix sont-elles dans la commune nouvelle ?
            cog = {}
            import csv
            with open(os.path.join(ROOT, "data", "raw", "v_commune_2026.csv"), encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    if r["TYPECOM"] in ("COMD", "COMA") and r["COMPARENT"]:
                        cog[r["COM"]] = r["COMPARENT"]
            rattachees = sum(1 for c in absents_ex if cog.get(c) in data)
            print(f"   communes absentes rattachées à une commune nouvelle (COG 2026) : {rattachees}/{len(absents_ex)}")
            print("   autres :", [c for c in absents_ex if cog.get(c) not in data][:20])
        for e in exemples:
            print("   ex.", e)


if __name__ == "__main__":
    main()
